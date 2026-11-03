"""
cat_features.py - extra pet + assistant features for Peeking Cat
=================================================================
Keep this file in the same folder as Main_file.pyw.  If it is missing or broken, the cat
still starts (the new menu items simply do not appear).

What is inside
  1. To-do list ............ tray > "To-do list...".  Tick a task and the cat celebrates.
                             Add "@tomorrow", "@fri" or "@2026-11-05" to a task to give it a due date.
  2. Cat reacts to apps .... looks at the NAME of the program in front (for example code.exe) and
                             says something or changes mood.  Nothing is stored, nothing leaves the PC.
                             Your own rules go in app_reactions.json (see AppReactions below).
  3. Purring + sounds ...... meow, mew, chirp, trill, squeak and a purr, all made by the program.
  4. Good night routine .... at your bedtime the cat says good night, shows tomorrow's first task,
                             curls up under a moon and sleeps.
  5. Stroll on the taskbar . the cat trots with little hops and a wagging tail, sometimes stops to
                             look around, sits for a moment, and trots back.
  6. Calendar import ....... reads an .ics file (Google Calendar / Outlook / university timetable)
                             and turns it into reminders.
  7. Study tracker ......... subjects, exam countdown, daily goal, streak, study timer and an
                             evening "did you study?" question.
"""
import calendar
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import struct
import sys
import threading
import time
import wave
from datetime import date, datetime, time as dtime, timedelta, timezone

from PySide6.QtCore import QDate, QPointF, QRectF, QTime, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox, QTimeEdit,
                               QVBoxLayout, QWidget)

import ctypes
try:
    from ctypes import wintypes
except Exception:                                   # very old / odd Pythons
    wintypes = None

try:
    import winsound                                 # Windows only
except ImportError:
    winsound = None

# ----------------------------------------------------------------------
# SETTINGS you can change
# ----------------------------------------------------------------------
GN_SAY_SECONDS = 10.0          # good night: how long the cat talks
GN_SLEEP_SECONDS = 26.0        # good night: how long the cat sleeps in front of you
GN_WINDOW_MINUTES = 120        # good night may start up to this long after your bedtime
STROLL_CHANCE = 0.12           # chance (0 to 1) that the cat goes for a stroll when it pops up
STROLL_COOLDOWN = 150.0        # seconds between two strolls
STROLL_SPEED = 0.85            # average walking speed in cat widths per second
GAIT_RATE = 11.5               # how fast the little legs step (radians per second at full speed)
APP_POLL_MS = 2000             # how often the cat looks at the program in front
APP_CONFIRM_SECONDS = 4.0      # you must stay in a program this long before the cat reacts
APP_COOLDOWN = 600.0           # the cat reacts to the same program at most once in 10 minutes
APP_GLOBAL_COOLDOWN = 40.0     # and never twice within 40 seconds
OVERWHELM_WINDOWS = 15         # "so many windows!" when this many programs are open
OVERWHELM_COOLDOWN = 1800.0
PURR_COOLDOWN = 12.0           # seconds between purrs

ORANGE = QColor(255, 143, 92)
BLUE = QColor(84, 138, 235)
NIGHT_ACCENT = QColor(110, 96, 200)
GREEN = QColor(60, 170, 120)
WHITE = QColor(255, 255, 255)
BUBBLE_BG = QColor(255, 251, 245)
BUBBLE_BORDER = QColor(236, 198, 166)
SHADOW = 14
TAIL = 14

EXTRA_STYLE = """
QProgressBar { background: #f3e3d3; border: none; border-radius: 5px; }
QProgressBar::chunk { background: #ff8f5c; border-radius: 5px; }
QSpinBox, QDateEdit, QTimeEdit { background: white; color: #2b2622; border: 1px solid #ead3bd;
                                 border-radius: 9px; padding: 5px 8px; font-size: 13px; }
QCheckBox { color: #2b2622; font-size: 13px; }
"""


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def read_json(path, default, backup_broken=False):
    """Read a JSON file. backup_broken=True: if the file exists but is broken, copy it to .bak first,
    because the next save would overwrite it (and the user's data would be gone)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        if backup_broken:
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
        return default


def write_json(path, data):
    """Write so that a crash can never leave a half-written file."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def parse_hhmm(text, default):
    try:
        hh, mm = [int(v) for v in str(text).strip().split(":")]
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return dtime(hh, mm)
    except Exception:
        pass
    return default


def force_topmost(widget):
    if sys.platform != "win32" or wintypes is None:
        return
    try:
        f = ctypes.windll.user32.SetWindowPos
        f.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        f.restype = wintypes.BOOL
        f(wintypes.HWND(int(widget.winId())), wintypes.HWND(-1), 0, 0, 0, 0,
          0x0001 | 0x0002 | 0x0010 | 0x0040)
    except Exception:
        pass


# ----------------------------------------------------------------------
# 3. SOUNDS: meow, mew, chirp, trill, squeak, purr (all generated, no files)
# ----------------------------------------------------------------------
RATE = 22050


def _to_wav(samples):
    peak = max(max(samples), -min(samples), 1e-6)
    data = struct.pack("<%dh" % len(samples), *[int(v / peak * 0.55 * 32767) for v in samples])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)
    return buf.getvalue()


def _bell(x):
    return smooth(x / 0.08) * (1.0 - smooth((x - 0.68) / 0.32))


def _voice(dur, pitch, formant, vib_rate=6.0, vib_depth=0.02, env=None, harmonics=13):
    """A singing voice: harmonics of a gliding pitch, shaped by a moving 'vowel' (formant)."""
    n = int(RATE * dur)
    phase = 0.0
    out = []
    for i in range(n):
        x = i / float(n)
        t = i / float(RATE)
        f0 = pitch(x) * (1.0 + vib_depth * math.sin(2.0 * math.pi * vib_rate * t))
        phase += 2.0 * math.pi * f0 / RATE
        fc = formant(x)
        s = 0.0
        for k in range(1, harmonics + 1):
            fk = k * f0
            if fk > RATE / 2.2:
                break
            s += (math.exp(-((fk - fc) / 700.0) ** 2) + 0.3 / k) * math.sin(k * phase)
        out.append(s * (env(x) if env else _bell(x)))
    return out


def _make_meow(rng):
    base, dur = rng.uniform(380, 560), rng.uniform(0.55, 0.9)

    def pitch(x):
        return base * (0.9 + 0.5 * smooth(x / 0.35)) if x < 0.35 else base * (1.4 - 0.75 * smooth((x - 0.35) / 0.65))
    return _voice(dur, pitch, lambda x: 2400.0 - 1650.0 * smooth((x - 0.15) / 0.5),
                  vib_rate=rng.uniform(5.5, 7.0))


def _make_mew(rng):
    base, dur = rng.uniform(640, 780), rng.uniform(0.26, 0.38)

    def pitch(x):
        return base * (0.95 + 0.3 * smooth(x / 0.5)) if x < 0.5 else base * (1.25 - 0.35 * smooth((x - 0.5) / 0.5))
    return _voice(dur, pitch, lambda x: 2700.0 - 900.0 * x)


def _make_chirp(rng):
    out = []
    for k in range(2):
        base = rng.uniform(750, 950) * (1.0 + 0.12 * k)
        out += _voice(0.11, lambda x, b=base: b * (0.85 + 0.5 * x), lambda x: 2900.0,
                      vib_depth=0.0, env=lambda x: smooth(x / 0.15) * (1.0 - smooth((x - 0.6) / 0.4)))
        out += [0.0] * int(RATE * 0.03)
    return out


def _make_trill(rng):
    base = rng.uniform(480, 580)
    return _voice(0.55, lambda x: base * (1.0 + 0.10 * x), lambda x: 2100.0,
                  vib_rate=24.0, vib_depth=0.13)


def _make_squeak(rng):
    base = rng.uniform(900, 1100)
    return _voice(0.16, lambda x: base * (0.9 + 0.4 * x), lambda x: 3000.0, vib_depth=0.0,
                  env=lambda x: smooth(x / 0.15) * (1.0 - smooth((x - 0.5) / 0.5)))


def _make_purr(rng):
    """About 25 soft pulses per second on a low, buzzy tone: a cat purring."""
    dur = 2.4
    n = int(RATE * dur)
    phase = 0.0
    noise = 0.0
    out = []
    for i in range(n):
        t = i / float(RATE)
        x = i / float(n)
        rate = 24.0 + 2.0 * math.sin(2.0 * math.pi * 0.7 * t)
        pulse = math.exp(-((t * rate) % 1.0) * 6.5)
        f0 = 105.0 + 7.0 * math.sin(2.0 * math.pi * 0.5 * t)
        phase += 2.0 * math.pi * f0 / RATE
        tone = sum(math.sin(k * phase) / k for k in range(1, 7))
        noise = noise * 0.88 + (rng.random() - 0.5) * 0.4
        env = smooth(x / 0.15) * (1.0 - smooth((x - 0.75) / 0.25))
        out.append((tone * 0.6 + noise * 1.1) * pulse * env)
    return out


_BUILDERS = {"meow": _make_meow, "mew": _make_mew, "chirp": _make_chirp, "trill": _make_trill,
             "squeak": _make_squeak, "purr": _make_purr}
SOUND_KINDS = tuple(_BUILDERS)
_CACHE = {}


def build_sound(kind, seed=None):
    """WAV bytes of one cat sound (kind is one of SOUND_KINDS)."""
    return _to_wav(_BUILDERS[kind](random.Random(seed if seed is not None else random.randint(0, 10 ** 6))))


def play_cat_sound(kind="random"):
    """Play a cat sound on a small background thread (Windows). kind = a name from SOUND_KINDS
    or "random" (a mix of meow, mew, chirp, trill and squeak)."""
    if winsound is None:
        return

    def run():
        try:
            k = kind
            if k == "random":
                k = random.choices(["meow", "mew", "chirp", "trill", "squeak"], [40, 25, 15, 10, 10])[0]
            if k not in _BUILDERS:
                return
            cache = _CACHE.setdefault(k, [])
            if len(cache) < 3:
                cache.append(build_sound(k))
                data = cache[-1]
            else:
                data = random.choice(cache)
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------------
# 2. what program is in front? (names only, nothing is recorded)
# ----------------------------------------------------------------------
def foreground_exe_name():
    """File name of the program whose window is in front, e.g. 'code.exe' ('' if unknown)."""
    if sys.platform != "win32" or wintypes is None:
        return ""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""


def count_open_windows():
    """How many normal program windows are open (0 if unknown)."""
    if sys.platform != "win32" or wintypes is None:
        return 0
    try:
        user32 = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        counter = [0]

        def callback(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
                    return True
                ex = user32.GetWindowLongW(hwnd, -20)
                if (ex & 0x80) and not (ex & 0x40000):               # tool window, not an app window
                    return True
                cloaked = wintypes.DWORD(0)
                dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value:
                    return True
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, 256)
                if title.value in ("Program Manager", "Settings"):
                    return True
                counter[0] += 1
            except Exception:
                pass
            return True
        user32.EnumWindows(proc_type(callback), 0)
        return counter[0]
    except Exception:
        return 0


IGNORED_APPS = {"python.exe", "pythonw.exe", "py.exe", "explorer.exe", "searchhost.exe",
                "startmenuexperiencehost.exe", "shellexperiencehost.exe", "applicationframehost.exe"}

_CODING = {"say": ["Coding time! You can do it!", "Bug hunting? I'm watching!", "Time to write some code!"],
           "mood": "happy"}
_READING = {"say": ["Reading time. Remember to rest your eyes!", "Good focus! Take a break soon."],
            "mood": "happy"}
_GAME = {"say": ["Game time! Good luck!", "Have fun! Don't forget water!"], "mood": "dance"}
_ART = {"say": ["Ooh, art time!", "Make something beautiful!"], "mood": "playful"}
_MEETING = {"say": ["Meeting time. I will be quiet."], "mood": None}

DEFAULT_APP_REACTIONS = {
    "code.exe": _CODING, "devenv.exe": _CODING, "pycharm64.exe": _CODING, "idea64.exe": _CODING,
    "clion64.exe": _CODING, "androidstudio64.exe": _CODING, "cursor.exe": _CODING,
    "windowsterminal.exe": {"say": ["Hacker cat mode!"], "mood": "happy"},
    "cmd.exe": {"say": ["Command line! So cool."], "mood": "happy"},
    "powershell.exe": {"say": ["Command line! So cool."], "mood": "happy"},
    "winword.exe": {"say": ["Writing time. Take your time!"], "mood": "happy"},
    "excel.exe": {"say": ["Numbers! I like numbers."], "mood": "happy"},
    "powerpnt.exe": {"say": ["Slides! Practise out loud."], "mood": "happy"},
    "acrobat.exe": _READING, "acrord32.exe": _READING, "sumatrapdf.exe": _READING,
    "spotify.exe": {"say": ["Music! La la la"], "mood": "singing"},
    "steam.exe": _GAME, "epicgameslauncher.exe": _GAME, "valorant-win64-shipping.exe": _GAME,
    "cs2.exe": _GAME, "dota2.exe": _GAME, "fortniteclient-win64-shipping.exe": _GAME,
    "robloxplayerbeta.exe": _GAME,
    "mspaint.exe": _ART, "figma.exe": _ART, "photoshop.exe": _ART,
    "zoom.exe": _MEETING, "teams.exe": _MEETING, "ms-teams.exe": _MEETING,
    "taskmgr.exe": {"say": ["Is something slow? I am watching!"], "mood": "confused"},
    "obs64.exe": {"say": ["Recording? Smile!"], "mood": "blush"},
    "discord.exe": {"say": ["Chatting with friends?"], "mood": "happy"},
}
REACT_MOODS = {"happy", "dance", "singing", "playful", "surprised", "blush", "confused", "love",
               "cry", "emotional", "angry", "sneeze", "yawn"}


class AppReactions:
    """Built-in reactions plus your own, from app_reactions.json in the cat folder, for example:

        {"chrome.exe": {"say": "Browsing?", "mood": "happy"},
         "code.exe":   null}                      <- null switches a built-in reaction off

    "say" is a text or a list of texts (one is picked at random). "mood" is one of:
    happy, dance, singing, playful, surprised, blush, confused, love, cry, emotional, angry, sneeze, yawn."""

    def __init__(self, path):
        self.rules = dict(DEFAULT_APP_REACTIONS)
        user = read_json(path, {})
        if isinstance(user, dict):
            for name, spec in user.items():
                key = str(name).strip().lower()
                if spec is None:
                    self.rules.pop(key, None)
                elif isinstance(spec, dict):
                    self.rules[key] = spec

    def get(self, exe):
        spec = self.rules.get(str(exe).lower())
        if not isinstance(spec, dict):
            return None
        say = spec.get("say", "")
        if isinstance(say, list):
            say = random.choice(say) if say else ""
        mood = spec.get("mood")
        return {"say": str(say), "mood": mood if isinstance(mood, str) and mood in REACT_MOODS else None}


# ----------------------------------------------------------------------
# a small non-interactive speech bubble above the cat
# ----------------------------------------------------------------------
class SayBubble(QWidget):
    def __init__(self, cat):
        super().__init__()
        self.cat = cat
        self.tail_x = 60
        self.accent = ORANGE
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(270 + 2 * SHADOW)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16 + SHADOW, 12 + SHADOW, 16 + SHADOW, 12 + TAIL + SHADOW)
        lay.setSpacing(4)
        self.badge = QLabel()
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setStyleSheet("font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #2b2622;")
        lay.addWidget(self.badge)
        lay.addWidget(self.body)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_text(self, text, seconds, badge, accent):
        self.accent = accent
        self.badge.setText(badge)
        self.badge.setStyleSheet("color: %s; font-size: 10px; font-weight: bold;" % accent.name())
        self.body.setText(text)
        lay = self.layout()
        lay.activate()
        h = lay.totalHeightForWidth(self.width())
        if h < 0:
            h = lay.sizeHint().height()
        self.setFixedHeight(h)
        self.place()
        if not self.isVisible():
            self.show()
            self.raise_()
            force_topmost(self)
        self.update()
        self.hide_timer.start(int(max(0.5, seconds) * 1000))

    def place(self):
        cat = self.cat
        a = QGuiApplication.primaryScreen().availableGeometry()
        cat_top = cat.y() + cat.pad + int((1.0 - cat.pos_) * cat.cat_h)
        center = cat.x() + cat.width() // 2
        x = max(a.x() - SHADOW + 8, min(center - self.width() // 2,
                                        a.x() + a.width() - self.width() + SHADOW - 8))
        y = max(a.y() - SHADOW, cat_top + 6 - (self.height() - SHADOW))
        tail = max(SHADOW + 28, min(center - x, self.width() - SHADOW - 28))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
        if tail != self.tail_x:
            self.tail_x = tail
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(SHADOW, SHADOW, self.width() - 2.0 * SHADOW, self.height() - 2.0 * SHADOW - TAIL)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(SHADOW, 0, -1):
            alpha = max(1, int(6 * (1.0 - (i - 1) / float(SHADOW)) ** 2))
            p.setBrush(QColor(70, 40, 20, alpha))
            p.drawRoundedRect(body.adjusted(-i, -i + 3, i, i + 3), 16 + i, 16 + i)
        path = QPainterPath()
        path.addRoundedRect(body, 16, 16)
        tail = QPainterPath()
        tx = float(self.tail_x)
        tail.moveTo(tx - 11, body.bottom() - 1)
        tail.lineTo(tx, body.bottom() + TAIL)
        tail.lineTo(tx + 11, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        p.setBrush(BUBBLE_BG)
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.setBrush(self.accent)
        p.drawRect(QRectF(body.left(), body.top(), body.width(), 4))
        p.restore()
        p.setPen(QPen(BUBBLE_BORDER, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


# ----------------------------------------------------------------------
# 1. TO-DO LIST (data)
# ----------------------------------------------------------------------
_DAY_WORDS = {}
for _i, _name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
    for _n in (3, 4, 5, len(_name)):
        _DAY_WORDS[_name[:_n]] = _i


def parse_date_word(word, today=None):
    """today, tomorrow, mon..sun, +3d, 2026-11-05, 5/11 (day/month) -> date, or None."""
    today = today or date.today()
    w = str(word).strip().lower()
    try:
        if w in ("today", "tod"):
            return today
        if w in ("tomorrow", "tmr", "tom"):
            return today + timedelta(days=1)
        if w in _DAY_WORDS:
            return today + timedelta(days=(_DAY_WORDS[w] - today.weekday()) % 7)
        m = re.fullmatch(r"\+(\d{1,3})d", w)
        if m:
            return today + timedelta(days=int(m.group(1)))
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", w)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", w)
        if m:
            year = int(m.group(3)) if m.group(3) else today.year
            d = date(year, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and d < today:
                d = date(year + 1, d.month, d.day)
            return d
    except ValueError:
        return None
    return None


def split_due(text, today=None):
    """'buy ink @tomorrow' -> ('buy ink', date).  Unknown @words stay in the text."""
    m = re.search(r"(?:^|\s)@([A-Za-z0-9/+\-]+)", text)
    if m:
        d = parse_date_word(m.group(1), today)
        if d is not None:
            clean = re.sub(r"\s+", " ", (text[:m.start()] + " " + text[m.end():])).strip()
            return clean, d
    return text.strip(), None


class TodoStore:
    def __init__(self, path):
        self.path = path
        self.items = []
        self.load()

    def load(self):
        data = read_json(self.path, {}, backup_broken=True)
        raw = data.get("items", []) if isinstance(data, dict) else []
        self.items = []
        used = set()
        for n, it in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(it, dict) or not str(it.get("text", "")).strip():
                continue
            item_id = it.get("id")
            if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id in used:
                item_id = int(time.time() * 1000) + n
                while item_id in used:
                    item_id += 1
            used.add(item_id)
            due = it.get("due") if isinstance(it.get("due"), str) else None
            try:
                if due:
                    date.fromisoformat(due)
            except ValueError:
                due = None
            self.items.append({"id": item_id, "text": str(it["text"]).strip(), "done": bool(it.get("done")),
                               "due": due or None, "created": str(it.get("created", "")),
                               "done_at": it.get("done_at") if isinstance(it.get("done_at"), str) else None})

    def save(self):
        write_json(self.path, {"items": self.items})

    def add(self, text, due=None):
        text = " ".join(str(text).split())
        if not text:
            return None
        used = {it["id"] for it in self.items}
        n = int(time.time() * 1000)
        while n in used:
            n += 1
        item = {"id": n, "text": text, "done": False, "due": due.isoformat() if due else None,
                "created": datetime.now().isoformat(timespec="seconds"), "done_at": None}
        self.items.append(item)
        self.save()
        return item

    def get(self, item_id):
        for it in self.items:
            if it["id"] == item_id:
                return it
        return None

    def set_done(self, item_id, done):
        it = self.get(item_id)
        if it is None:
            return None
        it["done"] = bool(done)
        it["done_at"] = datetime.now().isoformat(timespec="seconds") if done else None
        self.save()
        return it

    def delete(self, item_id):
        self.items = [it for it in self.items if it["id"] != item_id]
        self.save()

    def clear_done(self):
        self.items = [it for it in self.items if not it["done"]]
        self.save()

    def left(self):
        return sum(1 for it in self.items if not it["done"])

    def total(self):
        return len(self.items)

    def sorted_items(self):
        """Open tasks first (soonest due date first), finished tasks at the bottom."""
        def key(it):
            return (it["done"], it["due"] or "9999-99-99", it["created"])
        return sorted(self.items, key=key)


# ----------------------------------------------------------------------
# 6. CALENDAR (.ics) import
# ----------------------------------------------------------------------
_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _unescape(s):
    return s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _split_prop(line):
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _parse_dt(value, params):
    """-> (datetime in local time without tzinfo, all_day) or (None, False)."""
    value = value.strip()
    try:
        if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
            return datetime.strptime(value[:8], "%Y%m%d"), True
        utc = value.endswith("Z")
        core = value.rstrip("Z")
        d = datetime.strptime(core, "%Y%m%dT%H%M%S" if len(core) == 15 else "%Y%m%dT%H%M")
        if utc:
            try:
                d = d.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
            except Exception:
                pass
        elif params.get("TZID"):
            try:
                from zoneinfo import ZoneInfo
                d = d.replace(tzinfo=ZoneInfo(params["TZID"])).astimezone().replace(tzinfo=None)
            except Exception:
                pass                                   # unknown zone name: treat it as local time
        return d, False
    except ValueError:
        return None, False


def _parse_rrule(value):
    rule = {"freq": "", "interval": 1, "byday": [], "bymonthday": [], "count": None,
            "until": None, "unsupported": False}
    for part in value.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.upper(), v.strip()
        try:
            if k == "FREQ":
                rule["freq"] = v.upper()
            elif k == "INTERVAL":
                rule["interval"] = max(1, int(v))
            elif k == "COUNT":
                rule["count"] = int(v)
            elif k == "UNTIL":
                d, _ = _parse_dt(v, {})
                if d is not None:
                    rule["until"] = d + timedelta(days=1, seconds=-1) if len(v) == 8 else d
            elif k == "BYDAY":
                for tok in v.split(","):
                    m = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", tok.strip().upper())
                    if m and m.group(2) in _WD:
                        if m.group(1):
                            rule["unsupported"] = True        # e.g. "first Monday": not supported
                        rule["byday"].append(_WD[m.group(2)])
            elif k == "BYMONTHDAY":
                rule["bymonthday"] = [int(x) for x in v.split(",") if x.strip()]
            elif k in ("BYSETPOS", "BYWEEKNO", "BYYEARDAY"):
                rule["unsupported"] = True
        except ValueError:
            rule["unsupported"] = True
    return rule


def parse_ics(text):
    """Read the events of an .ics file. Returns a list of dicts (see keys below)."""
    events, cur, in_alarm = [], None, False
    for line in _unfold(text):
        up = line.strip().upper()
        if up == "BEGIN:VEVENT":
            cur, in_alarm = {"summary": "", "location": "", "uid": "", "start": None, "end": None,
                             "all_day": False, "rrule": None, "exdates": set(), "cancelled": False}, False
            continue
        if cur is None:
            continue
        if up == "BEGIN:VALARM":
            in_alarm = True
            continue
        if up == "END:VALARM":
            in_alarm = False
            continue
        if up == "END:VEVENT":
            if cur["start"] is not None and not cur["cancelled"]:
                cur["summary"] = cur["summary"] or "(no title)"
                if not cur["uid"]:
                    cur["uid"] = hashlib.md5((cur["summary"] + str(cur["start"])).encode("utf-8")).hexdigest()[:12]
                events.append(cur)
            cur = None
            continue
        if in_alarm:
            continue
        prop = _split_prop(line)
        if not prop:
            continue
        name, params, value = prop
        if name == "SUMMARY":
            cur["summary"] = _unescape(value).strip()
        elif name == "LOCATION":
            cur["location"] = _unescape(value).strip()
        elif name == "UID":
            cur["uid"] = value.strip()
        elif name == "DTSTART":
            cur["start"], cur["all_day"] = _parse_dt(value, params)
        elif name == "DTEND":
            cur["end"], _ = _parse_dt(value, params)
        elif name == "RRULE":
            cur["rrule"] = _parse_rrule(value)
        elif name == "EXDATE":
            for part in value.split(","):
                d, _ = _parse_dt(part, params)
                if d is not None:
                    cur["exdates"].add(d)
        elif name == "STATUS" and value.strip().upper() == "CANCELLED":
            cur["cancelled"] = True
    return events


def _gen_occurrences(start, rule):
    freq, interval = rule["freq"], max(1, rule["interval"])
    if freq == "DAILY":
        cur = start
        while True:
            yield cur
            cur += timedelta(days=interval)
    elif freq == "WEEKLY":
        days = sorted(set(rule["byday"])) or [start.weekday()]
        week = start - timedelta(days=start.weekday())
        while True:
            for wd in days:
                cand = week + timedelta(days=wd)
                if cand >= start:
                    yield cand
            week += timedelta(weeks=interval)
    elif freq == "MONTHLY" and not rule["byday"]:
        days = rule["bymonthday"] or [start.day]
        y, m = start.year, start.month
        for _ in range(12 * 200):                       # hard stop: at most 200 years of months
            last = calendar.monthrange(y, m)[1]
            for d in sorted({x if x > 0 else last + 1 + x for x in days if x != 0}):   # -1 = last day
                if 1 <= d <= last:
                    cand = start.replace(year=y, month=m, day=d)
                    if cand >= start:
                        yield cand
            m += interval
            y += (m - 1) // 12
            m = (m - 1) % 12 + 1
            if y > 9999:
                return
    elif freq == "YEARLY":
        for k in range(400):                            # hard stop, and never past year 9999
            try:
                yield start.replace(year=start.year + k * interval)
            except ValueError:
                pass                                    # e.g. 29 Feb in a non-leap year
    else:
        yield start


def expand_event(ev, win_start, win_end, cap=400):
    """Start times of an event (and of its repeats) inside [win_start, win_end)."""
    start, rule = ev["start"], ev.get("rrule")
    ex_days = {d.date() for d in (ev.get("exdates") or set())}

    def excluded(c):
        return c.date() in ex_days
    if not rule or not rule.get("freq") or rule.get("unsupported"):
        return [start] if (win_start <= start < win_end and not excluded(start)) else []
    out, produced, guard = [], 0, 0
    until, count = rule.get("until"), rule.get("count")
    for cand in _gen_occurrences(start, rule):
        guard += 1
        if guard > 20000:
            break
        if until and cand > until:
            break
        produced += 1
        if count and produced > count:
            break
        if cand >= win_end:
            break
        if cand >= win_start and not excluded(cand):
            out.append(cand)
            if len(out) >= cap:
                break
    return out


def _event_text(ev, when, lead):
    loc = ". %s" % ev["location"] if ev.get("location") else ""
    if ev.get("all_day"):
        return "Today: %s%s" % (ev["summary"], loc)
    if lead <= 0:
        return "%s starts now%s" % (ev["summary"], loc)
    return "%s starts at %s (in %d min)%s" % (ev["summary"], when.strftime("%H:%M"), lead, loc)


def build_import(events, now, lead, key, compute_next, horizon_days=120, reminder_days=90):
    """Turn parsed events into (reminder items, agenda entries, stats). No files are touched here.
    A plain weekly / daily class becomes ONE repeating reminder; everything else becomes one-time
    reminders for the next reminder_days days."""
    src = "ics:" + key
    lead_td = timedelta(minutes=lead)
    win_start = datetime.combine(now.date(), dtime.min)
    win_end = now + timedelta(days=horizon_days)
    items, agenda = [], []
    stats = {"events": len(events), "repeating": 0, "once": 0, "skipped": 0}
    for ev in events:
        occs = expand_event(ev, win_start, win_end, cap=300)
        dur = ev["end"] - ev["start"] if ev.get("end") and ev["end"] > ev["start"] else timedelta(0)
        for o in occs:
            agenda.append({"summary": ev["summary"], "start": o.isoformat(timespec="seconds"),
                           "end": (o + dur).isoformat(timespec="seconds"), "all_day": bool(ev["all_day"]),
                           "location": ev.get("location", "")})
        rule = ev.get("rrule")
        simple = bool(rule and rule.get("freq") in ("DAILY", "WEEKLY") and rule["interval"] == 1
                      and not rule.get("count") and not rule.get("until")
                      and not rule.get("unsupported") and not ev["all_day"])
        if simple:
            t0 = ev["start"] - lead_td
            shift = (t0.date() - ev["start"].date()).days            # 0, or -1 if the lead crosses midnight
            item = {"kind": "remind", "text": _event_text(ev, ev["start"], lead), "src": src,
                    "time": t0.strftime("%H:%M")}
            if rule["freq"] == "DAILY":
                item["repeat"] = "daily"
            else:
                days = sorted({(wd + shift) % 7 for wd in (rule["byday"] or [ev["start"].weekday()])})
                item["repeat"], item["days"] = "days", days
            nxt = compute_next(item, max(now, t0 - timedelta(minutes=1)))
            if nxt is not None:
                item["next"] = nxt.isoformat(timespec="seconds")
                items.append(item)
                stats["repeating"] += 1
            continue
        made = 0
        for o in occs:
            if o > now + timedelta(days=reminder_days) or made >= 40:
                break
            fire = o.replace(hour=8, minute=0) if ev["all_day"] else o - lead_td
            if fire <= now:
                stats["skipped"] += 1
                continue
            items.append({"kind": "remind", "text": _event_text(ev, o, lead), "repeat": "once",
                          "next": fire.isoformat(timespec="seconds"), "src": src})
            stats["once"] += 1
            made += 1
    return items[:400], agenda[:900], stats


# ----------------------------------------------------------------------
# 7. STUDY TRACKER (data)
# ----------------------------------------------------------------------
class StudyStore:
    def __init__(self, path):
        self.path = path
        self.subjects = []
        self.load()

    def load(self):
        data = read_json(self.path, {}, backup_broken=True)
        raw = data.get("subjects", []) if isinstance(data, dict) else []
        self.subjects = []
        used = set()
        for n, s in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(s, dict) or not str(s.get("name", "")).strip():
                continue
            sid = s.get("id")
            if not isinstance(sid, int) or isinstance(sid, bool) or sid in used:
                sid = int(time.time() * 1000) + n
                while sid in used:
                    sid += 1
            used.add(sid)
            exam = s.get("exam") if isinstance(s.get("exam"), str) else ""
            try:
                if exam:
                    date.fromisoformat(exam)
            except ValueError:
                exam = ""
            try:
                goal = min(600, max(5, int(s.get("goal", 30))))
            except (TypeError, ValueError):
                goal = 30
            log = {}
            if isinstance(s.get("log"), dict):
                for k, v in s["log"].items():
                    try:
                        date.fromisoformat(k)
                        log[k] = max(0, int(v))
                    except (TypeError, ValueError):
                        pass
            self.subjects.append({"id": sid, "name": str(s["name"]).strip(), "exam": exam,
                                  "goal": goal, "log": log})

    def save(self):
        write_json(self.path, {"subjects": self.subjects})

    def add(self, name, exam, goal):
        name = " ".join(str(name).split())
        if not name:
            return None
        used = {s["id"] for s in self.subjects}
        n = int(time.time() * 1000)
        while n in used:
            n += 1
        s = {"id": n, "name": name, "exam": exam.isoformat() if exam else "",
             "goal": min(600, max(5, int(goal))), "log": {}}
        self.subjects.append(s)
        self.save()
        return s

    def get(self, sid):
        for s in self.subjects:
            if s["id"] == sid:
                return s
        return None

    def delete(self, sid):
        self.subjects = [s for s in self.subjects if s["id"] != sid]
        self.save()

    def exam_date(self, s):
        try:
            return date.fromisoformat(s["exam"]) if s["exam"] else None
        except ValueError:
            return None

    def days_left(self, s, today=None):
        d = self.exam_date(s)
        return (d - (today or date.today())).days if d else None

    def minutes_on(self, s, d):
        return int(s["log"].get(d.isoformat(), 0))

    def log_minutes(self, sid, minutes, d=None):
        """Add minutes to a day. Returns (minutes before, minutes after) or None."""
        s = self.get(sid)
        if s is None or minutes <= 0:
            return None
        d = d or date.today()
        before = self.minutes_on(s, d)
        s["log"][d.isoformat()] = before + int(minutes)
        cutoff = (d - timedelta(days=400)).isoformat()
        s["log"] = {k: v for k, v in s["log"].items() if k >= cutoff}
        self.save()
        return before, before + int(minutes)

    def streak(self, s, today=None):
        """Days in a row (ending today, or yesterday if today is not finished yet) that met the goal."""
        today = today or date.today()
        d = today if self.minutes_on(s, today) >= s["goal"] else today - timedelta(days=1)
        n = 0
        while self.minutes_on(s, d) >= s["goal"] and n < 400:
            n += 1
            d -= timedelta(days=1)
        return n

    def last_days(self, s, count=7, today=None):
        today = today or date.today()
        return "".join("■" if self.minutes_on(s, today - timedelta(days=i)) >= s["goal"] else "□"
                       for i in range(count - 1, -1, -1))

    def sorted_subjects(self, today=None):
        today = today or date.today()

        def key(s):
            d = self.exam_date(s)
            if d is None:
                return (2, "", s["name"].lower())
            return (0 if d >= today else 1, d.isoformat(), s["name"].lower())
        return sorted(self.subjects, key=key)


def exam_phrase(days):
    if days is None:
        return "no exam date"
    if days < 0:
        return "exam was %d day%s ago" % (-days, "" if days == -1 else "s")
    if days == 0:
        return "EXAM TODAY"
    if days == 1:
        return "exam TOMORROW"
    return "exam in %d days" % days


# ----------------------------------------------------------------------
# the windows
# ----------------------------------------------------------------------
class _TodoList(QListWidget):
    def __init__(self, on_delete):
        super().__init__()
        self.on_delete = on_delete

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.on_delete()
            return
        super().keyPressEvent(event)


class TodoWindow(QDialog):
    def __init__(self, feats):
        super().__init__()
        self.f = feats
        self.setWindowTitle("Cat assistant - to-do list")
        self.setMinimumSize(520, 480)
        self.setStyleSheet(feats.style)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        title = QLabel("To-do list")
        title.setObjectName("h1")
        root.addWidget(title)
        self.progress = QLabel()
        root.addWidget(self.progress)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        root.addWidget(self.bar)
        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("What do you need to do?   e.g.  Submit lab report @fri")
        self.entry.returnPressed.connect(self.add_clicked)
        b_add = QPushButton("Add")
        b_add.setObjectName("primary")
        b_add.clicked.connect(lambda checked=False: self.add_clicked())
        row.addWidget(self.entry, 1)
        row.addWidget(b_add)
        root.addLayout(row)
        hint = QLabel("Tip: add @today, @tomorrow, @fri, @+3d or @2026-11-05 to give a task a due date.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.list = _TodoList(lambda: self.delete_selected())
        self.list.setWordWrap(True)
        self.list.itemChanged.connect(self.on_item_changed)
        root.addWidget(self.list, 1)
        row2 = QHBoxLayout()
        b_del = QPushButton("Delete selected")
        b_del.clicked.connect(lambda checked=False: self.delete_selected())
        b_clear = QPushButton("Clear finished")
        b_clear.clicked.connect(lambda checked=False: self.clear_done())
        b_close = QPushButton("Close")
        b_close.clicked.connect(lambda checked=False: self.hide())
        row2.addWidget(b_del)
        row2.addWidget(b_clear)
        row2.addStretch()
        row2.addWidget(b_close)
        root.addLayout(row2)
        self.refresh()

    def refresh(self):
        store = self.f.todo
        keep = self.selected_id()
        self.list.blockSignals(True)
        self.list.clear()
        today = date.today()
        for it in store.sorted_items():
            text = it["text"]
            if it["due"] and not it["done"]:
                try:
                    d = date.fromisoformat(it["due"])
                    when = d.strftime("%a %d %b")
                    if d < today:
                        text += "\n    overdue since %s" % when
                    elif d == today:
                        text += "\n    due TODAY"
                    else:
                        text += "\n    due %s" % when
                except ValueError:
                    pass
            row = QListWidgetItem(text)
            row.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                         | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked if it["done"] else Qt.CheckState.Unchecked)
            row.setData(Qt.ItemDataRole.UserRole, it["id"])
            if it["done"]:
                font = row.font()
                font.setStrikeOut(True)
                row.setFont(font)
                row.setForeground(QColor("#9a8f84"))
            self.list.addItem(row)
            if it["id"] == keep:
                self.list.setCurrentItem(row)
        if not store.items:
            empty = QListWidgetItem("Nothing here yet. Add your first task above.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        self.list.blockSignals(False)
        total, left = store.total(), store.left()
        done = total - left
        self.bar.setRange(0, max(1, total))
        self.bar.setValue(done)
        self.progress.setText("%d of %d done" % (done, total) if total else "No tasks yet")

    def selected_id(self):
        row = self.list.currentItem()
        return row.data(Qt.ItemDataRole.UserRole) if row is not None else None

    def add_clicked(self):
        text, due = split_due(self.entry.text())
        if not text:
            return
        self.f.todo.add(text, due)
        self.entry.clear()
        self.refresh()
        self.f.todo_changed()

    def on_item_changed(self, item):
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if item_id is None:
            return
        done = item.checkState() == Qt.CheckState.Checked
        self.f.set_todo_done(item_id, done)
        QTimer.singleShot(0, self.refresh)          # re-sort after the click is finished

    def delete_selected(self):
        item_id = self.selected_id()
        if item_id is not None:
            self.f.todo.delete(item_id)
            self.refresh()
            self.f.todo_changed()

    def clear_done(self):
        self.f.todo.clear_done()
        self.refresh()
        self.f.todo_changed()


class StudyWindow(QDialog):
    def __init__(self, feats):
        super().__init__()
        self.f = feats
        self.setWindowTitle("Cat assistant - study tracker")
        self.setMinimumSize(640, 640)
        self.setStyleSheet(feats.style)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        title = QLabel("Study tracker")
        title.setObjectName("h1")
        root.addWidget(title)
        self.sub = QLabel()
        self.sub.setObjectName("hint")
        self.sub.setWordWrap(True)
        root.addWidget(self.sub)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setMinimumHeight(190)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Log study time for the selected subject:"))
        row.addStretch()
        for minutes in (15, 30, 60):
            b = QPushButton("+%d min" % minutes)
            b.clicked.connect(lambda checked=False, m=minutes: self.log(m))
            row.addWidget(b)
        b_custom = QPushButton("Other...")
        b_custom.clicked.connect(lambda checked=False: self.log_custom())
        row.addWidget(b_custom)
        root.addLayout(row)
        row2 = QHBoxLayout()
        b_timer = QPushButton("Start a study timer...")
        b_timer.setObjectName("primary")
        b_timer.clicked.connect(lambda checked=False: self.start_timer())
        b_del = QPushButton("Delete subject")
        b_del.clicked.connect(lambda checked=False: self.delete_subject())
        row2.addWidget(b_timer)
        row2.addWidget(b_del)
        row2.addStretch()
        root.addLayout(row2)

        root.addWidget(QLabel("Add a subject:"))
        form = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Subject, e.g. Data Structures")
        self.name.returnPressed.connect(self.add_subject)
        self.has_exam = QCheckBox("Exam on")
        self.exam = QDateEdit()
        self.exam.setCalendarPopup(True)
        self.exam.setDisplayFormat("ddd d MMM yyyy")
        soon = date.today() + timedelta(days=14)
        self.exam.setDate(QDate(soon.year, soon.month, soon.day))
        self.exam.setEnabled(False)
        self.has_exam.toggled.connect(self.exam.setEnabled)
        self.goal = QSpinBox()
        self.goal.setRange(5, 600)
        self.goal.setValue(30)
        self.goal.setSuffix(" min/day")
        b_add = QPushButton("Add")
        b_add.setObjectName("primary")
        b_add.clicked.connect(lambda checked=False: self.add_subject())
        form.addWidget(self.name, 1)
        form.addWidget(self.has_exam)
        form.addWidget(self.exam)
        form.addWidget(self.goal)
        form.addWidget(b_add)
        root.addLayout(form)

        row3 = QHBoxLayout()
        self.checkin_on = QCheckBox("Ask me every evening if I studied, at")
        self.checkin_on.setChecked(bool(feats.opt("study_checkin_on", True)))
        self.checkin_on.toggled.connect(lambda v: feats.set_opt("study_checkin_on", bool(v)))
        self.checkin_time = QTimeEdit()
        self.checkin_time.setDisplayFormat("HH:mm")
        t = parse_hhmm(feats.opt("study_checkin", "20:00"), dtime(20, 0))
        self.checkin_time.setTime(QTime(t.hour, t.minute))
        self.checkin_time.timeChanged.connect(
            lambda qt: feats.set_opt("study_checkin", "%02d:%02d" % (qt.hour(), qt.minute())))
        b_close = QPushButton("Close")
        b_close.clicked.connect(lambda checked=False: self.hide())
        row3.addWidget(self.checkin_on)
        row3.addWidget(self.checkin_time)
        row3.addStretch()
        row3.addWidget(b_close)
        root.addLayout(row3)
        self.refresh()

    def describe(self, s):
        store = self.f.study
        today = date.today()
        mins = store.minutes_on(s, today)
        total = sum(s["log"].values())
        exam = store.exam_date(s)
        head = "%s   -   %s" % (s["name"], exam_phrase(store.days_left(s, today)))
        if exam:
            head += " (%s)" % exam.strftime("%a %d %b")
        streak = store.streak(s, today)
        return "%s\nToday %d of %d min   -   streak %d day%s   -   last 7 days %s   -   total %dh %02dm" % (
            head, mins, s["goal"], streak, "" if streak == 1 else "s", store.last_days(s), total // 60, total % 60)

    def refresh(self):
        keep = self.selected_id()
        self.list.clear()
        subjects = self.f.study.sorted_subjects()
        for s in subjects:
            row = QListWidgetItem(self.describe(s))
            row.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.list.addItem(row)
            if s["id"] == keep:
                self.list.setCurrentItem(row)
        if not subjects:
            empty = QListWidgetItem("No subjects yet. Add one below.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        elif self.list.currentItem() is None:
            self.list.setCurrentRow(0)
        met = sum(1 for s in subjects if self.f.study.minutes_on(s, date.today()) >= s["goal"])
        self.sub.setText("Today: %d of %d subjects reached their daily goal." % (met, len(subjects))
                         if subjects else "Add your subjects and exam dates. The cat counts down for you.")

    def selected_id(self):
        row = self.list.currentItem()
        return row.data(Qt.ItemDataRole.UserRole) if row is not None else None

    def need_selection(self):
        sid = self.selected_id()
        if sid is None:
            QMessageBox.information(self, "Study tracker", "Click a subject in the list first.")
        return sid

    def add_subject(self):
        name = self.name.text().strip()
        if not name:
            return
        exam = None
        if self.has_exam.isChecked():
            q = self.exam.date()
            exam = date(q.year(), q.month(), q.day())
        self.f.study.add(name, exam, self.goal.value())
        self.name.clear()
        self.refresh()

    def log(self, minutes):
        sid = self.need_selection()
        if sid is not None:
            self.f.log_study(sid, minutes)
            self.refresh()

    def log_custom(self):
        sid = self.need_selection()
        if sid is None:
            return
        minutes, ok = QInputDialog.getInt(self, "Study tracker", "Minutes studied:", 45, 1, 720)
        if ok:
            self.f.log_study(sid, minutes)
            self.refresh()

    def start_timer(self):
        sid = self.need_selection()
        if sid is None:
            return
        s = self.f.study.get(sid)
        if s is None:
            self.refresh()
            return
        minutes, ok = QInputDialog.getInt(self, "Study timer", "Study for how many minutes?",
                                          min(60, max(5, s["goal"])), 1, 600)
        if ok:
            self.f.start_study_timer(sid, minutes)
            self.hide()                              # so you can see the cat and its timer bubble

    def delete_subject(self):
        sid = self.need_selection()
        if sid is None:
            return
        s = self.f.study.get(sid)
        if s is None:
            self.refresh()
            return
        if QMessageBox.question(self, "Study tracker", "Delete '%s' and its study log?" % s["name"]) \
                == QMessageBox.StandardButton.Yes:
            self.f.study.delete(sid)
            self.refresh()


# ----------------------------------------------------------------------
# the manager: Main_file.pyw only talks to this class
# ----------------------------------------------------------------------
class CatFeatures:
    def __init__(self, cat, base_dir, window_style, compute_next):
        self.cat = cat
        self.base = base_dir
        self.style = window_style + EXTRA_STYLE
        self.compute_next = compute_next
        self.todo = TodoStore(os.path.join(base_dir, "todos.json"))
        self.study = StudyStore(os.path.join(base_dir, "study.json"))
        self.calendar_file = os.path.join(base_dir, "calendar_events.json")
        self.apps = AppReactions(os.path.join(base_dir, "app_reactions.json"))
        self.say_bubble = SayBubble(cat)
        self.todo_window = None
        self.study_window = None
        self.todo_action = None
        self.bedtime_action = None

        self._say_until = 0.0
        self.last_purr = 0.0
        self.last_walk = 0.0
        self.gn_phase = None            # None, "say", "sleep"
        self.gn_t0 = 0.0
        self.gn_sleep_t0 = 0.0
        self.w_phase = None
        self.w_t0 = 0.0
        self.w_dur = 1.0
        self.w_target = 0.0
        self.w_sit = 4.0
        self.w_has_pause = False
        self.w_pause = False
        self.w_gait = 0.0
        self.w_speed = 0.0
        self.w_dir = 1
        self._w_prev = 0.0
        self._app = ""
        self._app_since = 0.0
        self._app_done = True
        self._app_last = {}
        self._last_react = 0.0
        self._last_overwhelm = 0.0
        self._cursor = QCursor.pos()
        self._active_at = time.time()
        pending = cat.saved.get("study_pending")
        self.study_pending = pending if isinstance(pending, dict) else None

        self.sec_timer = QTimer(cat)
        self.sec_timer.setInterval(1000)
        self.sec_timer.timeout.connect(self._every_second)
        self.sec_timer.start()
        self.app_timer = QTimer(cat)
        self.app_timer.setInterval(APP_POLL_MS)
        self.app_timer.timeout.connect(self._poll_apps)
        self.app_timer.start()

    def opt(self, key, default):
        return self.cat.saved.get(key, default)

    def set_opt(self, key, value):
        self.cat.saved[key] = value
        self.cat.save_settings()

    def sounds_on(self):
        return bool(self.opt("meow", True))

    def say(self, text, seconds=4.0, badge="CAT", accent=None):
        self._say_until = time.perf_counter() + seconds
        self.say_bubble.show_text(text, seconds, badge, accent or ORANGE)

    def say_visible(self):
        return self.say_bubble.isVisible()

    def react(self, text, mood=None, seconds=4.0, sound=None, badge="CAT", accent=None):
        """The cat comes out, shows a mood and says something."""
        now = time.perf_counter()
        if mood in REACT_MOODS:
            self.cat.timed[mood] = now + seconds
        self.cat.wake()
        if text:
            self.say(text, seconds, badge, accent)
        if sound and self.sounds_on():
            play_cat_sound(sound)

    def _user_active(self, seconds):
        return time.time() - self._active_at <= seconds

    def _free_for_event(self):
        """True when nothing else (chat, arcade, feeding, pause, do-not-disturb) has the cat's attention."""
        cat = self.cat
        a = cat.assistant
        if cat.paused or cat.big_mode or a.dnd or a.busy() or cat.feed is not None:
            return False
        try:
            if a.rps.is_active():
                return False
        except Exception:
            pass
        return True

    def forced_emotion(self, now):
        """The good night routine decides the face while it runs (None = no opinion)."""
        if self.gn_phase == "say":
            return "talk" if now - self.gn_t0 < 3.5 else "sleepy"
        if self.gn_phase == "sleep":
            return "sleeping"
        return None

    def walk_emotion(self):
        return "happy" if self.w_phase in ("out", "back") and not self.w_pause else None

    def gait(self):
        """Describes the stroll for the drawing code (None when the cat is not strolling)."""
        if self.w_phase is None:
            return None
        if self.w_phase == "sit" or self.w_pause:
            return {"mode": "sit", "phase": self.w_gait, "speed": 0.0, "dir": self.w_dir}
        return {"mode": "walk", "phase": self.w_gait, "speed": self.w_speed, "dir": self.w_dir}

    def keep_out(self):
        """True while the cat must stay up and not slide down."""
        return (self.gn_phase is not None or self.w_phase is not None
                or time.perf_counter() < self._say_until)

    def curl_amount(self, t):
        """0..1: how curled up the sleeping cat is (good night routine only)."""
        if self.gn_phase == "sleep":
            return smooth((t - self.gn_sleep_t0) / 1.6)
        return 0.0

    def on_petted(self):
        """Called while you hold the pointer on the cat: it purrs."""
        now = time.time()
        if not self.opt("purr", True) or now - self.last_purr < PURR_COOLDOWN:
            return
        self.last_purr = now
        play_cat_sound("purr")

    def on_timer_started(self, minutes):
        if self.study_pending is not None:
            self.study_pending = None
            self.cat.saved.pop("study_pending", None)
            self.cat.save_settings()

    def on_timer_cancelled(self):
        self.on_timer_started(0)

    def on_timer_done(self, minutes):
        """The cat timer ended: if it was a study timer, write the minutes into the study log."""
        p = self.study_pending
        if not p:
            return
        self.study_pending = None
        self.cat.saved.pop("study_pending", None)
        self.cat.save_settings()
        if p.get("minutes") == minutes and self.study.get(p.get("id")) is not None:
            self.log_study(p["id"], minutes, from_timer=True)

    def maybe_walk(self, now):
        """Called every time the cat pops up: sometimes it goes for a stroll."""
        if (self.opt("stroll", True) and random.random() < STROLL_CHANCE
                and now - self.last_walk > STROLL_COOLDOWN and self.w_phase is None
                and self.gn_phase is None):
            QTimer.singleShot(1000, self._begin_walk)

    def shutdown(self):
        for t in (self.sec_timer, self.app_timer):
            t.stop()
        self.say_bubble.hide()
        for w in (self.todo_window, self.study_window):
            if w is not None:
                w.close()

    def tick(self, now):
        if self.say_bubble.isVisible():
            if self.cat.assistant.busy():
                self.say_bubble.hide()
            else:
                self.say_bubble.place()
        self._tick_goodnight(now)
        self._tick_walk(now)

    def _every_second(self):
        pos = QCursor.pos()
        if pos != self._cursor:
            self._cursor = pos
            self._active_at = time.time()
        now_dt = datetime.now()
        try:
            self._check_bedtime(now_dt)
            self._check_study_checkin(now_dt)
        except Exception as err:                   # a bug here must never stop the cat
            self._log("scheduler: %r" % (err,))

    def _log(self, text):
        try:
            with open(os.path.join(self.base, "cat_error.log"), "a", encoding="utf-8") as f:
                f.write("[%s] features: %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
        except OSError:
            pass

    def open_todo(self):
        if self.todo_window is None:
            self.todo_window = TodoWindow(self)
        self.todo_window.refresh()
        self.todo_window.show()
        self.todo_window.raise_()
        self.todo_window.activateWindow()

    def todo_changed(self):
        self.update_menu()

    def set_todo_done(self, item_id, done):
        it = self.todo.set_done(item_id, done)
        self.update_menu()
        if it is None or not done:
            return
        total, left = self.todo.total(), self.todo.left()
        if left == 0:
            self.react("All tasks done! Great job!", "dance", 5.0, "chirp", "TO-DO", GREEN)
        else:
            self.react("Nice! %d of %d done." % (total - left, total), "happy", 2.5, "chirp", "TO-DO", GREEN)

    def _poll_apps(self):
        if not self.opt("react_apps", True):
            return
        exe = foreground_exe_name()
        now = time.time()
        if exe != self._app:
            self._app, self._app_since, self._app_done = exe, now, False
            return
        if self._app_done or not exe or now - self._app_since < APP_CONFIRM_SECONDS:
            return
        self._app_done = True
        if exe in IGNORED_APPS or not self._free_for_event() or self.gn_phase is not None:
            return
        self._react_to_app(exe, now)
        self._check_overwhelmed(now)

    def _react_to_app(self, exe, now):
        spec = self.apps.get(exe)
        if spec is None:
            return
        if now - self._last_react < APP_GLOBAL_COOLDOWN or now - self._app_last.get(exe, 0.0) < APP_COOLDOWN:
            return
        self._last_react = self._app_last[exe] = now
        self.react(spec["say"], spec["mood"], 4.5, "chirp" if spec["mood"] else None, "I SEE YOU")

    def _check_overwhelmed(self, now):
        if now - self._last_overwhelm < OVERWHELM_COOLDOWN or now - self._last_react < 8.0:
            return
        limit = self.opt("overwhelm_windows", OVERWHELM_WINDOWS)
        if count_open_windows() >= limit:
            self._last_overwhelm = self._last_react = now
            self.react("So many windows open! Maybe close a few?", "confused", 5.0, "squeak", "WHOA")

    def _plan_day(self, now_dt=None):
        """The day the cat should preview: tomorrow (or today, if it is already after midnight)."""
        now_dt = now_dt or datetime.now()
        return now_dt.date() if now_dt.hour < 5 else now_dt.date() + timedelta(days=1)

    def _check_bedtime(self, now_dt):
        if not self.opt("goodnight", True) or self.gn_phase is not None:
            return
        bed = parse_hhmm(self.opt("bedtime", "23:00"), dtime(23, 0))
        for back in (0, 1):
            day = now_dt.date() - timedelta(days=back)
            start = datetime.combine(day, bed)
            if start <= now_dt < start + timedelta(minutes=GN_WINDOW_MINUTES):
                key = day.isoformat()
                if self.opt("goodnight_date", "") == key:
                    return
                if not self._user_active(240) or not self._free_for_event():
                    return                           # wait until you are at the PC and the cat is free
                self.set_opt("goodnight_date", key)
                self.start_goodnight()
                return

    def tomorrow_first(self, day):
        """(first thing of that day as text or None, how many other things there are)."""
        exams, timed, untimed = [], [], []
        for s in self.study.subjects:
            if self.study.exam_date(s) == day:
                exams.append("EXAM: " + s["name"])
        for ev in self.events_between(datetime.combine(day, dtime.min), datetime.combine(day, dtime.max)):
            if ev["all_day"]:
                untimed.append(ev["summary"])
            else:
                timed.append((ev["start"], "%s  %s" % (ev["start"].strftime("%H:%M"), ev["summary"])))
        for it in self.cat.assistant.items:
            if str(it.get("src", "")).startswith("ics:") or it.get("kind") != "remind":
                continue
            try:
                due = datetime.fromisoformat(it["next"])
            except Exception:
                continue
            if due.date() == day:
                timed.append((due, "%s  %s" % (due.strftime("%H:%M"), it.get("text", ""))))
        for it in self.todo.items:
            if not it["done"] and it["due"] == day.isoformat():
                untimed.append("To-do: " + it["text"])
        timed.sort(key=lambda x: x[0])
        everything = exams + [t for _, t in timed] + untimed
        if exams:
            first = exams[0]
        elif timed:
            first = timed[0][1]
        elif untimed:
            first = untimed[0]
        else:
            open_tasks = [it for it in self.todo.sorted_items() if not it["done"]]
            if open_tasks:
                return "To-do: " + open_tasks[0]["text"], max(0, len(open_tasks) - 1)
            return None, 0
        return first, max(0, len(everything) - 1)

    def goodnight_text(self):
        day = self._plan_day()
        lines = ["Good night! Sleep well."]
        first, more = self.tomorrow_first(day)
        if first:
            lines.append("First thing %s: %s" % ("tomorrow" if day > date.today() else "today", first))
            if more:
                lines.append("(and %d more thing%s)" % (more, "" if more == 1 else "s"))
        else:
            lines.append("Nothing planned for %s. Rest well!" % ("tomorrow" if day > date.today() else "today"))
        near = [(self.study.days_left(s, day), s["name"]) for s in self.study.subjects
                if self.study.days_left(s, day) is not None and 0 < self.study.days_left(s, day) <= 7]
        if near:
            days, name = min(near)
            lines.append("%s exam in %d day%s." % (name, days, "" if days == 1 else "s"))
        return "\n".join(lines)

    def start_goodnight(self, manual=False):
        if self.gn_phase is not None:
            return False
        if not self._free_for_event():
            if manual:
                self.say("Not now, I am busy. Try again in a moment.", 3.0)
            return False
        self._end_walk(snap=True)
        now = time.perf_counter()
        self.gn_phase, self.gn_t0 = "say", now
        self.cat.wake()
        self.say(self.goodnight_text(), GN_SAY_SECONDS - 0.5, "GOOD NIGHT", NIGHT_ACCENT)
        if self.sounds_on():
            play_cat_sound("mew")
        return True

    def _tick_goodnight(self, now):
        if self.gn_phase is None:
            return
        cat = self.cat
        if cat.paused or cat.big_mode or cat.assistant.busy():
            self._end_goodnight()
            return
        el = now - self.gn_t0
        if self.gn_phase == "say" and el >= GN_SAY_SECONDS:
            self.gn_phase, self.gn_t0, self.gn_sleep_t0 = "sleep", now, now
            if self.opt("purr", True):
                play_cat_sound("purr")
        elif self.gn_phase == "sleep" and el >= GN_SLEEP_SECONDS:
            self._end_goodnight()

    def _end_goodnight(self):
        self.gn_phase = None
        self.say_bubble.hide()

    def draw_night(self, p, t, base):
        """A moon and twinkling stars over the sleeping cat (picture pixels, called from draw_symbols)."""
        if self.gn_phase is None:
            return
        alpha = base * smooth((t - self.gn_t0) / 1.2)
        if alpha <= 0.02:
            return
        p.save()
        p.setOpacity(alpha)
        cx, cy, r = 520.0, -360.0, 210.0
        moon = QPainterPath()
        moon.addEllipse(QPointF(cx, cy), r, r)
        cut = QPainterPath()
        cut.addEllipse(QPointF(cx + r * 0.62, cy - r * 0.18), r * 0.86, r * 0.86)
        pen = QPen(WHITE, r * 0.12)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(QColor(255, 214, 102))
        p.drawPath(moon.subtracted(cut))
        for i, (sx, sy, size) in enumerate(((930, -640, 90), (1230, -330, 64), (250, -700, 70), (850, -250, 48))):
            s = size * (0.65 + 0.35 * math.sin(t * 2.4 + i * 1.7))
            star = QPainterPath()
            star.moveTo(sx, sy - s)
            star.quadTo(sx, sy, sx + s, sy)
            star.quadTo(sx, sy, sx, sy + s)
            star.quadTo(sx, sy, sx - s, sy)
            star.quadTo(sx, sy, sx, sy - s)
            p.setPen(QPen(WHITE, size * 0.12))
            p.setBrush(QColor(255, 238, 150))
            p.drawPath(star)
        p.restore()

    def ask_bedtime(self):
        cur = self.opt("bedtime", "23:00")
        text, ok = QInputDialog.getText(None, "Bedtime", "Your usual bedtime (24-hour, HH:MM):", text=cur)
        if not ok:
            return
        t = parse_hhmm(text, None)
        if t is None:
            QMessageBox.information(None, "Bedtime", "Please type the time like 23:30")
            return
        self.set_opt("bedtime", t.strftime("%H:%M"))
        self.update_menu()

    def stroll_now(self):
        cat = self.cat
        if cat.mood != "auto":
            self.say("Set my Mood to Auto, then I can go for a stroll!", 3.5)
            return
        if not cat.mover.is_home():
            self.say("Put me back on the taskbar first, then I can go for a stroll!", 3.5)
            return
        cat.wake()
        QTimer.singleShot(700, self._begin_walk)

    def _begin_walk(self):
        cat = self.cat
        if self.w_phase is not None or self.gn_phase is not None:
            return
        # cat.rise() is 1.0 when the cat is fully up. (The old test "pos_ < 0.6" was always true with
        # SHOW_FRACTION = 0.6, because the spring only gets very close to 0.6, so the cat never strolled.)
        rise = cat.rise() if hasattr(cat, "rise") else cat.pos_
        if cat.mood != "auto" or not self._free_for_event() or rise < 0.9 or not cat.mover.is_home():
            return
        a = QGuiApplication.primaryScreen().availableGeometry()
        w = cat.cat_w
        room_left = cat.x() - a.x()
        room_right = a.x() + a.width() - (cat.x() + cat.width())
        options = [(room_left, -1), (room_right, 1)]
        options = [(room, sign) for room, sign in options if room >= 1.1 * w]
        if not options:
            return
        options.sort(reverse=True)
        room, sign = options[0] if (len(options) == 1 or random.random() < 0.7) else options[1]
        dist = min(room - 8, random.uniform(1.3, 3.2) * w, 0.4 * a.width())
        self.w_target = sign * dist
        self.w_has_pause = dist > 2.0 * w and random.random() < 0.6
        self.w_dur = max(1.6, dist / (w * STROLL_SPEED)) * (1.15 if self.w_has_pause else 1.0)
        self.w_sit = random.uniform(3.5, 6.0)
        self.w_gait, self.w_speed, self.w_pause, self.w_dir = 0.0, 0.0, False, sign
        self.w_phase, self.w_t0 = "out", time.perf_counter()
        self._w_prev = self.last_walk = self.w_t0

    def _walk_curve(self, f):
        """Distance walked (0..1) and walking speed (0..1) after a fraction f of the trip.
        The cat eases into the walk, eases out of it, and may stop once in the middle."""
        if not self.w_has_pause:
            return smooth(f), 4.0 * f * (1.0 - f)
        if f < 0.45:
            x = f / 0.45
            return 0.5 * smooth(x), 4.0 * x * (1.0 - x)
        if f < 0.55:
            return 0.5, 0.0
        x = (f - 0.55) / 0.45
        return 0.5 + 0.5 * smooth(x), 4.0 * x * (1.0 - x)

    def _tick_walk(self, now):
        if self.w_phase is None:
            return
        cat = self.cat
        if (cat.mood != "auto" or cat.paused or cat.big_mode or not cat.mover.is_home()
                or cat.assistant.busy() or cat.feed is not None or self.gn_phase is not None):
            self._end_walk(snap=True)
            return
        dt = min(0.05, max(0.0, now - self._w_prev))
        self._w_prev = now
        el = now - self.w_t0
        offset = self.w_target
        if self.w_phase in ("out", "back"):
            f = min(1.0, el / self.w_dur)
            pos, spd = self._walk_curve(f)
            pause = self.w_has_pause and 0.45 <= f < 0.55
            if pause and not self.w_pause and self.sounds_on() and random.random() < 0.5:
                play_cat_sound("mew")
            self.w_pause = pause
            self.w_speed = 0.0 if pause else 0.2 + 0.8 * spd
            self.w_gait += dt * self.w_speed * GAIT_RATE
            if self.w_phase == "out":
                self.w_dir = 1 if self.w_target > 0 else -1
                offset = self.w_target * pos
            else:
                self.w_dir = -1 if self.w_target > 0 else 1
                offset = self.w_target * (1.0 - pos)
            offset += self.w_dir * 0.015 * cat.cat_w * math.sin(2.0 * self.w_gait) * self.w_speed
            if f >= 1.0:
                if self.w_phase == "back":
                    self._end_walk()
                    return
                self.w_phase, self.w_t0 = "sit", now
                self.w_speed, self.w_pause = 0.0, False
                offset = self.w_target
                if self.sounds_on() and random.random() < 0.6:
                    play_cat_sound("mew")
        else:
            self.w_speed = 0.0
            if el >= self.w_sit:
                self.w_phase, self.w_t0 = "back", now
        cat.walk_offset = offset
        cat.reposition()

    def _end_walk(self, snap=False):
        if self.w_phase is None and not snap:
            return
        self.w_phase = None
        self.w_speed, self.w_pause = 0.0, False
        self.cat.walk_offset = 0.0
        self.cat.reposition()

    def import_calendar_dialog(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose a calendar file", "",
                                              "Calendar files (*.ics);;All files (*)")
        if not path:
            return
        lead = int(self.opt("calendar_lead", 15))
        try:
            msg = self.import_calendar(path, lead)
        except Exception as err:
            self._log("import %s: %r" % (path, err))
            msg = "Sorry, I could not read that file:\n%s" % err
        QMessageBox.information(None, "Calendar import", msg)

    def import_calendar(self, path, lead=15):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            events = parse_ics(f.read())
        if not events:
            return "I did not find any events in that file."
        key = hashlib.md5(os.path.basename(path).lower().encode("utf-8")).hexdigest()[:8]
        a = self.cat.assistant
        now = datetime.now()
        items, agenda, stats = build_import(events, now, lead, key, self.compute_next)
        a.items = [it for it in a.items if it.get("src") != "ics:" + key]      # a second import replaces the first
        base = a.new_id()
        for n, it in enumerate(items):
            it["id"] = base + n
        a.items.extend(items)
        a.items.sort(key=lambda it: it["next"])
        a.save_items()
        a.refresh_window()
        store = read_json(self.calendar_file, {})
        files = store.get("files") if isinstance(store, dict) and isinstance(store.get("files"), dict) else {}
        files[key] = {"name": os.path.basename(path), "imported": now.isoformat(timespec="seconds"), "events": agenda}
        write_json(self.calendar_file, {"files": files})
        return ("Imported '%s'\n\n%d events found\n%d repeating reminders (weekly / daily classes)\n"
                "%d one-time reminders (next 90 days)\n%d already in the past, skipped\n\n"
                "Each reminder comes %d minutes before the event. Importing the same file again "
                "replaces these reminders." % (os.path.basename(path), stats["events"], stats["repeating"],
                                               stats["once"], stats["skipped"], lead))

    def remove_calendar(self):
        a = self.cat.assistant
        before = len(a.items)
        a.items = [it for it in a.items if not str(it.get("src", "")).startswith("ics:")]
        a.save_items()
        a.refresh_window()
        try:
            os.remove(self.calendar_file)
        except OSError:
            pass
        QMessageBox.information(None, "Calendar import",
                                "Removed %d imported reminders and the saved agenda." % (before - len(a.items)))

    def ask_lead(self):
        minutes, ok = QInputDialog.getInt(None, "Calendar import", "Remind me how many minutes before an event?\n"
                                          "(used the next time you import a file)",
                                          int(self.opt("calendar_lead", 15)), 0, 1440)
        if ok:
            self.set_opt("calendar_lead", minutes)

    def events_between(self, start, end):
        """Imported events that start in [start, end], soonest first."""
        out = []
        store = read_json(self.calendar_file, {})
        files = store.get("files", {}) if isinstance(store, dict) else {}
        for info in files.values():
            for ev in info.get("events", []) if isinstance(info, dict) else []:
                try:
                    s = datetime.fromisoformat(ev["start"])
                except Exception:
                    continue
                if start <= s <= end:
                    out.append({"summary": str(ev.get("summary", "")), "start": s, "all_day": bool(ev.get("all_day")),
                                "location": str(ev.get("location", ""))})
        out.sort(key=lambda e: e["start"])
        return out

    def show_agenda(self):
        now = datetime.now()
        events = self.events_between(datetime.combine(now.date(), dtime.min),
                                     datetime.combine(now.date() + timedelta(days=7), dtime.max))
        if not events:
            text = "Nothing on your calendar for the next 7 days.\n(Import an .ics file first.)"
        else:
            lines, last = [], None
            for ev in events:
                if ev["start"].date() != last:
                    last = ev["start"].date()
                    lines.append("\n" + last.strftime("%A %d %B"))
                when = "all day" if ev["all_day"] else ev["start"].strftime("%H:%M")
                loc = "  (%s)" % ev["location"] if ev["location"] else ""
                lines.append("  %s   %s%s" % (when, ev["summary"], loc))
            text = "\n".join(lines).strip()
        QMessageBox.information(None, "Next 7 days", text)

    def open_study(self):
        if self.study_window is None:
            self.study_window = StudyWindow(self)
        self.study_window.refresh()
        self.study_window.show()
        self.study_window.raise_()
        self.study_window.activateWindow()

    def log_study(self, sid, minutes, from_timer=False):
        s = self.study.get(sid)
        res = self.study.log_minutes(sid, minutes)
        if s is None or res is None:
            return
        before, after = res
        goal = s["goal"]
        if before < goal <= after:
            self.react("Goal reached for %s! %d day streak." % (s["name"], self.study.streak(s)),
                       "dance", 5.0, "chirp", "STUDY", GREEN)
        else:
            head = "Study timer done! " if from_timer else ""
            self.react("%s+%d min for %s. Today: %d of %d min." % (head, minutes, s["name"], after, goal),
                       "happy", 3.5, "chirp", "STUDY", GREEN)
        if self.study_window is not None:
            self.study_window.refresh()

    def start_study_timer(self, sid, minutes):
        s = self.study.get(sid)
        if s is None:
            return
        self.cat.timer_sys.start(minutes)               # this clears any older study link ...
        self.study_pending = {"id": sid, "minutes": int(minutes)}     # ... so the new one is set afterwards
        self.cat.saved["study_pending"] = self.study_pending
        self.cat.save_settings()

    def _check_study_checkin(self, now_dt):
        if not self.opt("study_checkin_on", True) or not self.study.subjects:
            return
        today = now_dt.date().isoformat()
        if self.opt("study_checkin_date", "") == today:
            return
        if now_dt.time() < parse_hhmm(self.opt("study_checkin", "20:00"), dtime(20, 0)):
            return
        if not self._user_active(180):
            return
        self.set_opt("study_checkin_date", today)
        lines = []
        for s in self.study.sorted_subjects(now_dt.date()):
            days = self.study.days_left(s, now_dt.date())
            if days is not None and days < 0:
                continue
            mins = self.study.minutes_on(s, now_dt.date())
            if mins >= s["goal"]:
                continue
            tag = "   (%s!)" % exam_phrase(days) if days is not None and days <= 3 else ""
            lines.append("%s: %d of %d min%s" % (s["name"], mins, s["goal"], tag))
        if not lines:
            return
        text = "Did you study today?\n" + "\n".join(lines[:6]) + "\nTray > Study tracker to log your time."
        a = self.cat.assistant
        a.queue.append(({"id": -3, "kind": "remind", "text": text, "repeat": "once"}, timedelta(0)))
        a.show_next()

    def add_menu(self, menu, add):
        """Called by Main_file.pyw: adds To-do, Study and Calendar to the main tray menu."""
        self.todo_action = add(menu, "To-do list...", self.open_todo)
        add(menu, "Study tracker...", self.open_study)
        cal = menu.addMenu("Calendar")
        add(cal, "Import .ics file...", self.import_calendar_dialog)
        add(cal, "Show the next 7 days", self.show_agenda)
        add(cal, "Reminder lead time...", self.ask_lead)
        cal.addSeparator()
        add(cal, "Remove imported events", self.remove_calendar)
        menu.aboutToShow.connect(self.update_menu)
        self.update_menu()

    def add_pet_menu(self, pet_menu, add):
        """Called by Main_file.pyw: adds the pet switches to 'Play with the cat'."""
        pet_menu.addSeparator()
        for text, key in (("React to my apps", "react_apps"), ("Stroll along the taskbar", "stroll"),
                          ("Purr when petted", "purr"), ("Good night routine", "goodnight")):
            act = pet_menu.addAction(text)
            act.setCheckable(True)
            act.setChecked(bool(self.opt(key, True)))
            act.toggled.connect(lambda value, k=key: self.set_opt(k, bool(value)))
        self.bedtime_action = add(pet_menu, "Set bedtime...", self.ask_bedtime)
        add(pet_menu, "Good night now", lambda: self.start_goodnight(manual=True))
        add(pet_menu, "Stroll now", self.stroll_now)
        add(pet_menu, "Purr now", lambda: play_cat_sound("purr"))
        add(pet_menu, "Random cat sound", lambda: play_cat_sound("random"))
        pet_menu.addSeparator()
        self.update_menu()

    def update_menu(self):
        if self.todo_action is not None:
            left = self.todo.left()
            self.todo_action.setText("To-do list (%d left)..." % left if left else "To-do list...")
        if self.bedtime_action is not None:
            self.bedtime_action.setText("Set bedtime (now %s)..." % self.opt("bedtime", "23:00"))
