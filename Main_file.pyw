"""
Peeking Cat
-----------
A cute cat pops up from behind the taskbar (right next to the clock) whenever
you move the mouse. Its eyes follow your cursor. When you stop moving the
mouse for a few seconds, the cat slides back down.

Setup:
    1. Install Python 3.9 or newer from python.org
    2. pip install PySide6 ollama
    3. Keep these files and cat.png in the same folder:
         Main_file.pyw, ai_assistant.py, cat_features.py, mini_game.py,
         cat_motion.py, notes.py, screen_ocr.py, weather.py, kitten.py, youtube_music.py
    4. Run:  python Main_file.pyw        (or double-click)
   If one of the extra files is missing or broken, the cat still starts (that feature is just missing;
   the reason is written to cat_error.log).

Pick the cat up: press on the cat and drag it. Let go and it falls. It sits on top of the window it
lands on (move the window and the cat rides along), or goes home if it lands on the taskbar.
Click the cat = pet it.  Double-click a sitting cat = it jumps down.  Right-click the cat = this menu.

The cat has feelings. In "Auto" mood it reacts by itself:
    - happy      when you come back after a while, or when it first starts
    - surprised  when you flick the mouse very fast (and when you pick it up)
    - angry      when you keep shaking the mouse around
    - in love    when you hold the mouse pointer on the cat, or click it
    - sad        when the laptop battery is low (15% or less, not charging)
    - crying, emotional, blush, sleepy (11 pm to 5 am), confused (mouse wiggling left and right),
      sleeping, whistling, dancing, singing, playful, sneezing and yawning now and then
Right-click the tray icon > Play with the cat > Mood to pick a feeling yourself, or back to Auto.

AI chat: tray > "Chat with the cat". Needs Ollama (ollama.com) and a model, e.g. run once in a
terminal:  ollama pull llama3.2
The cat can DO things from the chat: "remind me friday at 8pm to submit the lab report",
"add buy printer ink to my to-do list for tomorrow", "start a 25 minute timer",
"log 45 minutes of physics". The conversation is remembered (chat_history.json).
Enter = send, Shift+Enter = new line, Esc = stop the answer.

Read text from the screen: tray > "Read text from screen...", drag a box over any text and the
cat reads it (Windows OCR, offline). Then copy it or ask the cat to explain / summarize / translate.

Reminders: double-click the tray icon (or tray > "Reminders...") and type a sentence, e.g.
    in 20 minutes drink water  |  at 5pm call mom  |  tomorrow at 9 ask what are my top 3 tasks?
    every weekday at 9:30 stand-up  |  every 45 min stretch
Reminders are kept in reminders.json, so they survive restarts.

Sticky notes: tray > Sticky notes. Many notes, 7 colours, pin a note on top of all windows,
search all notes (notes.json).

Weather: tray > Weather > "Set my city...". The cat warns you when rain is coming and holds an
umbrella while it rains (open-meteo.com, no account needed).

A small kitten visits the cat now and then (tray > Play with the cat > Kitten visits).

YouTube music: tray > "YouTube music" > "Search and play...". Search YouTube (or paste a link) and
only the SOUND is played, no video. Needs once:  pip install -U "yt-dlp[default]"  and Deno or
Node.js installed. While a song plays the cat stays up, sings along and dances to it (it sings for
a while, then dances for a while, again and again), and it says hello when YouTube is open in your
browser. Tray > YouTube music > "Test: ..." shows you at once that these reactions work.

Timer, feeding (fish / milk), Cat Arcade (8 mini games), to-do list, study tracker, calendar
import and the good night routine are in the tray menu too.

Visual alerts: a reminder, timer or rain alert is also shown as a Windows pop-up notification,
because a chime means nothing to a deaf person (tray > Play with the cat > Pop-up notifications).
Do not disturb (tray): reminders wait, and the cat does not pop up with news.

To start the cat automatically when you log in to Windows: tray > "Start with Windows".
To quit: tray > Quit.
"""
import sys
sys.dont_write_bytecode = True

import json
import math
import os
import random
import re
import shutil
import tempfile
import threading
import time
import traceback

import ctypes
_MODULE_ERRORS = {}                        # extra file -> why it could not be loaded (written to cat_error.log)
try:
    from cat_features import CatFeatures, play_cat_sound, parse_date_word
except Exception as _err:                   # the cat must still start without the extra features
    CatFeatures = play_cat_sound = parse_date_word = None
    _MODULE_ERRORS["cat_features.py"] = repr(_err)
try:
    from mini_game import GameManager
except Exception as _err:                   # the cat must still start without the arcade
    _MODULE_ERRORS["mini_game.py"] = repr(_err)

    class GameManager:
        def __init__(self, assistant):
            self.assistant = assistant

        def is_active(self):
            return False

        def start_game(self):
            QMessageBox.information(None, "Peeking Cat", "The Cat Arcade could not be loaded "
                                    "(mini_game.py). See cat_error.log.")
try:
    from cat_motion import CatMover
except Exception as _err:
    _MODULE_ERRORS["cat_motion.py"] = repr(_err)

    class CatMover:                         # without cat_motion.py the cat simply cannot be picked up
        place = "home"
        tilt = 0.0

        def __init__(self, cat):
            pass

        def is_home(self):
            return True

        def in_air(self):
            return False

        def paws_visible(self):
            return True

        def emotion(self, now):
            return None

        def squash(self, now):
            return 1.0

        def update_input(self):
            pass

        def tick(self, dt, now):
            return False

        def go_home(self):
            pass

        def apply(self):
            pass

        def press(self, gpos):
            pass

        def move(self, gpos):
            pass

        def release(self, gpos):
            pass

        def double_click(self):
            pass
try:
    from notes import NotesManager
except Exception as _err:
    NotesManager = None
    _MODULE_ERRORS["notes.py"] = repr(_err)
try:
    from screen_ocr import ScreenReader
except Exception as _err:
    ScreenReader = None
    _MODULE_ERRORS["screen_ocr.py"] = repr(_err)
try:
    from weather import WeatherService
except Exception as _err:
    WeatherService = None
    _MODULE_ERRORS["weather.py"] = repr(_err)
try:
    from kitten import Kitten
except Exception as _err:
    Kitten = None
    _MODULE_ERRORS["kitten.py"] = repr(_err)
try:
    from youtube_music import YouTubeService
except Exception as _err:
    YouTubeService = None
    _MODULE_ERRORS["youtube_music.py"] = repr(_err)

# The AI backend lives in ai_assistant.py (same folder). If that file is missing or broken, the
# cat must still start (with a .pyw there is no console to show the error), so fall back to a stub.
try:
    from ai_assistant import LocalAIAssistant, clean_reply, DEFAULT_MODEL
    _AI_IMPORT_ERROR = ""
except Exception as _ai_err:
    _AI_IMPORT_ERROR = repr(_ai_err)
    _MODULE_ERRORS["ai_assistant.py"] = _AI_IMPORT_ERROR
    DEFAULT_MODEL = "llama3.2"

    def clean_reply(text):
        return str(text).strip()

    class LocalAIAssistant:
        busy = False
        partial = ""
        model_name = DEFAULT_MODEL

        def __init__(self, model_name=DEFAULT_MODEL, host=None, history_file=None, tool_handler=None):
            self.model_name = model_name

        def available(self):
            return False

        def set_model(self, name):
            pass

        def reset(self):
            pass

        def cancel(self):
            pass

        def list_models(self):
            return []

        def ask_async(self, prompt, on_chunk=None, on_complete=None, on_error=None, context=None,
                      allow_tools=True):
            if on_error:
                on_error("ai_assistant.py could not be loaded (%s). Keep it in the same folder "
                         "as this program." % _AI_IMPORT_ERROR)
            return False
if sys.platform == "win32":
    from ctypes import wintypes

try:
    import winreg          # Windows only (used for "Start with Windows")
except ImportError:
    winreg = None

try:
    import winsound        # Windows only (soft reminder chime)
except ImportError:
    winsound = None

from datetime import datetime, timedelta

from PySide6.QtCore import (Qt, QDate, QEasingCurve, QLockFile, QPointF, QPropertyAnimation,
                            QRectF, QTime, QTimer)
from PySide6.QtGui import (QActionGroup, QBrush, QLinearGradient, QRadialGradient, QColor, QCursor,
                           QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QTextCursor, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QSystemTrayIcon,
                               QTimeEdit, QVBoxLayout, QWidget, QWidgetAction)

# ----------------------------------------------------------------------
# SETTINGS you can change
# ----------------------------------------------------------------------
IMAGE_FILE = "cat.png"        # the cat picture, in the same folder as this file
CAT_WIDTH = 130               # starting size of the cat, in pixels
SIZE_PRESETS = [("Tiny", 110), ("Small", 150), ("Medium", 190),
                ("Large", 250), ("Extra large", 330)]
SIZE_STEP = 15                # how much "Bigger" / "Smaller" changes the size
MIN_WIDTH, MAX_WIDTH = 70, 600
POSITION_STEP = 0.06          # how far "Move left" / "Move right" moves the cat (0 to 1 of the screen width)
SETTINGS_FILE = "settings.json"   # remembers the size and position you picked from the tray menu
RIGHT_MARGIN = 0              # extra gap from the right edge (0 = cat touches the edge)
BIG_SCREEN_FRACTION = 1.0     # big-cat mode (Cat Arcade): the biggest the cat may get (part of the screen height)
SHOW_FRACTION = 0.6       # 0.7 = only the head peeks up (1.0 = whole cat comes out)
IDLE_HIDE_SECONDS = 3.0       # cat hides after this many seconds without mouse movement
MOVE_THRESHOLD = 4            # pixels the mouse must move to wake the cat

EYE_MAX_X = 80                # how far the eyes travel sideways (picture pixels)
EYE_MAX_Y = 62                # how far the eyes travel up and down
EYE_RANGE_PX = 240            # cursor distance at which the eyes reach full travel
BLINK_DURATION = 0.30         # seconds for one blink
BLINK_EVERY = (2.5, 6.0)      # random time between blinks, in seconds

# --- feelings -----------------------------------------------------------
HAPPY_AFTER_HIDDEN = 20.0     # happy when you return after the cat was hidden this many seconds
SURPRISE_SPEED = 2800         # mouse speed (pixels per second) that surprises the cat
SHAKE_SPEED = 1800            # mouse speed that counts as "shaking"
SHAKE_SECONDS = 1.8           # seconds of shaking before the cat gets angry
LOW_BATTERY_PERCENT = 15      # cat is sad at or below this battery level (when not charging)
NIGHT_HOURS = (23, 5)         # sleepy from 23:00 until 05:00
CONFUSE_TURNS = 5             # this many left-right turns of the mouse ...
CONFUSE_WINDOW = 2.0          # ... within this many seconds make the cat confused
IDLE_MOOD_AFTER = 1.0         # seconds without mouse movement before the cat whistles or falls asleep
WHISTLE_CHANCE = 0.35         # chance (0 to 1) that the cat whistles while it waits (daytime)
FUN_CHANCE = 0.18             # chance (0 to 1) that the cat dances or sings when it pops up
SNEEZE_CHANCE = 0.07          # chance (0 to 1) that the cat sneezes when it pops up
YAWN_CHANCE = 0.08            # chance that the cat yawns when it pops up (daytime)
YAWN_NIGHT_CHANCE = 0.30      # chance that the cat yawns when it pops up (at night)
SNEEZE_SECONDS = 3.2          # how long one sneeze takes
YAWN_SECONDS = 4.2            # how long one yawn takes
ANIM_STAY_SECONDS = 9.0       # a sneezing or yawning cat stays out this long (so it can finish)
SLEEP_STAY_SECONDS = 7.0      # a sleeping cat stays out this long, so you can see the zzz
FUN_STAY_SECONDS = 6.0        # a dancing, singing or whistling cat stays out this long
MOODS = [("Auto (reacts by itself)", "auto"), ("Normal", "normal"), ("Happy", "happy"),
         ("Blush", "blush"), ("Emotional", "emotional"), ("Crying", "cry"), ("Sad", "sad"),
         ("Sleepy", "sleepy"), ("Surprised", "surprised"), ("In love", "love"),
         ("Angry", "angry"), ("Confused", "confused"),
         ("Sleeping (zzz)", "sleeping"), ("Dancing", "dance"),
         ("Whistling", "whistle"), ("Singing", "singing"), ("Playful", "playful"),
         ("Sneezing", "sneeze"), ("Yawning", "yawn")]

# --- feeding ------------------------------------------------------------
FOODS = {"fish": "Fish", "milk": "Milk"}
FEED_ARRIVE_SECONDS = 0.8     # the food drops in / rises up
FISH_EAT_SECONDS = 5.5        # how long the cat takes to eat the fish
MILK_DRINK_SECONDS = 5.0      # how long the cat takes to drink the milk
FEED_DONE_SECONDS = 2.4       # happy time afterwards (hearts)
FISH_BITES = 4                # the fish is eaten in this many bites
FEED_LIMIT = 4                # the cat is full after this many meals ...
FEED_LIMIT_MINUTES = 90       # ... within this many minutes (set FEED_LIMIT to 999 for never full)
FEED_LOG_MAX = 300            # how many past meals to remember
FISH_COLOR = QColor(255, 146, 72)       # fin colour (bright orange)
FISH_LIGHT = QColor(255, 208, 150)
FISH_FIN_DARK = QColor(214, 92, 40)     # fin rays
FISH_FLESH = QColor(255, 138, 130)      # pink flesh where the cat has bitten
FISH_FLESH_LIGHT = QColor(255, 198, 186)
BONE_COLOR = QColor(255, 252, 240)
BOWL_COLOR = QColor(255, 250, 242)      # cream ceramic bowl
BOWL_INSIDE = QColor(214, 196, 172)
BOWL_BAND = QColor(112, 182, 238)       # blue stripe round the bowl
BOWL_PAW = QColor(255, 146, 170)
MILK_COLOR = QColor(255, 255, 255)
MILK_EDGE = QColor(200, 218, 240)

# --- reminders ------------------------------------------------------------
REMINDERS_FILE = "reminders.json"
CHAT_HISTORY_FILE = "chat_history.json"   # the AI chat is remembered here between runs
SNOOZE_MINUTES = 10
ASK_LATER_MINUTES = 30
REMINDER_SOUND = True
BUBBLE_WIDTH = 330
SNOOZE_CHOICES = [("5 minutes", 5), ("10 minutes", 10), ("30 minutes", 30),
                  ("1 hour", 60), ("3 hours", 180)]
ASK_STEALS_FOCUS = False      # True = a question grabs the keyboard at once (can swallow what you are typing elsewhere)
TYPE_SPEED_MS = 28            # speed of the typed-out message in the bubble

SPRING_K = 240.0
SPRING_C = 31.0
# ----------------------------------------------------------------------

REF_W = 3610.0
EYES = [(1244.5, 1116.0), (2353.5, 1116.0)]
COVERS = [QRectF(1040, 925, 410, 380), QRectF(2150, 925, 410, 380)]
FUR = QColor(255, 245, 235)
DARK = QColor(38, 38, 38)
EYE_RX, EYE_RY = 100.0, 128.0
PAD = 36
HEADROOM = 0.36
PAW_DROP = 215.0              # how far the paws reach down into the taskbar (picture pixels)
PAW_SCALE = 1.4               # size of the paws (1.0 = small, bigger = bigger paws)
PAW_SPREAD = 0.25             # the paws sit this far (part of the body width) left and right of the body's middle
PAW_BODY_ROWS = (0.50, 0.70)  # the body's middle is measured at the taskbar edge, but only inside this part of
                              # the picture (higher up are the whiskers, lower down is the tail)
BODY_ALPHA = 40               # a picture pixel counts as "cat" from this opacity (0..255)
DANCE_SPEED = 7.0             # how fast the dance goes (radians per second): one sway left and right = 0.9 s
DANCE_LEAN = 0.10             # how far the body leans over the paw that carries the weight (sideways shear)
DANCE_BOUNCE = 0.020          # how far the body bobs up and down (part of the cat's height)
DANCE_SQUASH = 0.03           # stretch when the body is up, squash when it is down
DANCE_PAW_LIFT = 135.0        # how high the free paw is lifted (picture pixels)
DANCE_PAW_SWING = 40.0        # how far the free paw swings out sideways (picture pixels)
DANCE_PAW_TILT = 11.0         # how much the free paw tilts outwards (degrees)
HEART = QColor(255, 82, 120)
TEAR = QColor(80, 180, 255)
TEAR_BORDER = QColor(30, 120, 220)
WHITE = QColor(255, 255, 255)
REL_COVER = QRectF(-205, -191, 410, 380)
NOTE_COLORS = [QColor(150, 90, 230), QColor(255, 110, 170), QColor(60, 170, 230), QColor(255, 170, 50)]
ZZZ_COLOR = QColor(90, 140, 235)
SNEEZE_COLOR = QColor(255, 120, 60)
YAWN_COLOR = QColor(120, 150, 215)
SPRAY = QColor(170, 222, 255)
QUESTION_COLOR = QColor(255, 150, 30)
TONGUE = QColor(255, 120, 140)
CHEEK = QColor(255, 140, 160, 110)
BLUSH_CHEEK = QColor(255, 100, 130, 170)
BLUSH_HATCH = QColor(230, 50, 90, 220)
MOUTH_DEFAULT = (1807.0, 1332.0, 266.0, 166.0)
MOUTH_COVER = QRectF(1648, 1236, 320, 190)
SYMBOL_MOODS = ("confused", "sleeping", "dance", "singing", "whistle", "sneeze", "yawn")

# --- playful mood (tail + butterflies) ------------------------------------
TAIL_BASE = (2400.0, 2330.0)  # where the tail starts (hidden behind the body), picture pixels
TAIL_LENGTH = 1150.0          # length of the tail
TAIL_FILL_W = 125.0           # width of the fur inside the tail
TAIL_OUTLINE_W = 60.0         # thickness of the dark outline
TAIL_WAG_SPEED = 7.0          # how fast the tail wags (bigger = faster)
TAIL_WAG_SIZE = 0.38          # how far the tail swings (radians)
BUTTERFLY_SIZE = 190.0        # size of the butterflies (picture pixels)
BUTTERFLY_COLORS = [(QColor(255, 130, 185), QColor(255, 190, 215)),
                    (QColor(160, 120, 245), QColor(205, 185, 255)),
                    (QColor(255, 175, 55), QColor(255, 220, 130))]
# each butterfly: centre x, centre y, radius x, radius y, speed (negative = other way), start angle
BUTTERFLIES = [(1800.0, 700.0, 1330.0, 1000.0, 0.85, 0.0),
               (1800.0, 560.0, 1000.0, 1000.0, -0.62, 2.1),
               (1800.0, 760.0, 1250.0, 800.0, 0.48, 4.2)]


def force_topmost(widget):
    if sys.platform != "win32":
        return
    try:
        f = ctypes.windll.user32.SetWindowPos
        f.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        f.restype = wintypes.BOOL
        HWND_TOPMOST = wintypes.HWND(-1)
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0010, 0x0040
        f(wintypes.HWND(int(widget.winId())), HWND_TOPMOST, 0, 0, 0, 0,
          SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        pass


def place_behind(widget, ref_widget):
    """Put `widget` directly behind `ref_widget` in the Windows stacking order (not topmost any more)."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        f = user32.SetWindowPos
        f.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        f.restype = wintypes.BOOL
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        flags = 0x0001 | 0x0002 | 0x0010          # NOSIZE | NOMOVE | NOACTIVATE
        me = wintypes.HWND(int(widget.winId()))
        ref = wintypes.HWND(int(ref_widget.winId()))
        nxt = user32.GetWindow(ref, 2)            # GW_HWNDNEXT: the window just below the options
        if nxt and int(nxt) == int(me.value or 0) and not (user32.GetWindowLongW(me, -20) & 0x8):
            return                                # already directly behind the options: nothing to do
        f(me, wintypes.HWND(-2), 0, 0, 0, 0, flags)      # HWND_NOTOPMOST: stop being above everything
        f(me, ref, 0, 0, 0, 0, flags)                    # sit right behind the options window
    except Exception:
        pass


def lowest_window(widgets):
    """Of several open windows, the one that is lowest in the stacking order (Windows)."""
    if sys.platform != "win32" or len(widgets) == 1:
        return widgets[-1]
    try:
        user32 = ctypes.windll.user32
        user32.GetTopWindow.argtypes = [wintypes.HWND]
        user32.GetTopWindow.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        wanted = {int(w.winId()): w for w in widgets}
        lowest = None
        h = user32.GetTopWindow(None)
        for _ in range(4000):                      # walk the windows from the top of the stack downwards
            if not h:
                break
            if int(h) in wanted:
                lowest = wanted[int(h)]            # the last one we meet is the lowest
            h = user32.GetWindow(h, 2)             # GW_HWNDNEXT
        return lowest or widgets[-1]
    except Exception:
        return widgets[-1]


# Windows' own panels (Wi-Fi, volume, calendar, Start...) live in a layer ABOVE normal always-on-top
# windows. While one is open, the taskbar is raised above the cat too, so it covers the part of the
# paws that hangs down over the taskbar. We cannot draw above that layer, so the paws are hidden then.
SYSTEM_PANEL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                        "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow",
                        "ControlCenterWindow", "Windows.UI.Core.CoreWindow"}


def system_panel_open():
    """True while the window in front is the taskbar or one of Windows' flyouts (Wi-Fi, volume...)."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value in SYSTEM_PANEL_CLASSES
    except Exception:
        return False


def battery_is_low():
    if sys.platform != "win32":
        return False
    try:
        class PowerStatus(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        st = PowerStatus()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            return st.ACLineStatus == 0 and st.BatteryLifePercent <= LOW_BATTERY_PERCENT
    except Exception:
        pass
    return False


def is_night():
    hour = time.localtime().tm_hour
    return hour >= NIGHT_HOURS[0] or hour < NIGHT_HOURS[1]


def fade_loop(prog):
    return min(1.0, prog / 0.15) * min(1.0, (1.0 - prog) / 0.3)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def yawn_amount(ph):
    """How wide the yawn is (0 = closed, 1 = widest) at phase ph (0..1) of one yawn."""
    if ph < 0.5:
        return smooth(ph / 0.5)
    if ph < 0.72:
        return 1.0
    return 1.0 - smooth((ph - 0.72) / 0.22)


def sneeze_build(ph):
    """The 'ah... ah...' build-up before the sneeze (0..1), 0 once the sneeze has happened."""
    return smooth(ph / 0.56) if ph < 0.58 else 0.0


def sneeze_burst(ph):
    """The 'ACHOO!' itself: snaps to 1 quickly, then fades away (0..1)."""
    return smooth((ph - 0.58) / 0.04) * (1.0 - smooth((ph - 0.78) / 0.14))


def draw_word(p, text, x, y, px, color, alpha, angle=0.0, grow=1.0):
    """Bold comic-style word with a white outline, centred on (x, y)."""
    font = QFont("Segoe UI")
    font.setPixelSize(int(px))
    font.setBold(True)
    path = QPainterPath()
    path.addText(0, 0, font, text)
    br = path.boundingRect()
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.scale(grow, grow)
    p.translate(-br.center().x(), -br.center().y())
    p.setOpacity(max(0.0, min(1.0, alpha)))
    edge = QPen(WHITE, px * 0.18)
    edge.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(edge)
    p.setBrush(color)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)
    p.restore()


def stroke_symbol(p, path, x, y, width, color, alpha, angle):
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.setOpacity(alpha)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for col, w in ((WHITE, width * 1.7), (color, width)):
        pen = QPen(col, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
    p.restore()


def draw_z(p, x, y, size, color, alpha, angle=0.0):
    u = size
    path = QPainterPath()
    path.moveTo(-0.55 * u, -0.6 * u)
    path.lineTo(0.55 * u, -0.6 * u)
    path.lineTo(-0.55 * u, 0.6 * u)
    path.lineTo(0.55 * u, 0.6 * u)
    stroke_symbol(p, path, x, y, 0.27 * u, color, alpha, angle)


def draw_question(p, x, y, size, color, alpha, angle=0.0):
    u = size
    path = QPainterPath()
    path.moveTo(-0.62 * u, -0.62 * u)
    path.cubicTo(-0.62 * u, -1.45 * u, 0.68 * u, -1.45 * u, 0.68 * u, -0.62 * u)
    path.cubicTo(0.68 * u, -0.1 * u, 0.0, -0.2 * u, 0.0, 0.42 * u)
    path.moveTo(0.0, 0.98 * u)
    path.lineTo(0.0, 0.981 * u)
    stroke_symbol(p, path, x, y, 0.3 * u, color, alpha, angle)


def draw_music_note(p, x, y, size, color, alpha, double=False, angle=0.0):
    u = size
    path = QPainterPath()
    heads = [(0.0, 0.0, -1.6), (1.15, -0.18, -1.78)] if double else [(0.0, 0.0, -1.6)]
    for hx, hy, stem_top in heads:
        head = QPainterPath()
        head.addEllipse(QPointF(0, 0), 0.5 * u, 0.36 * u)
        tr = QTransform()
        tr.translate(hx * u, hy * u)
        tr.rotate(-20)
        path.addPath(tr.map(head))
        path.addRect(QRectF((hx + 0.38) * u, stem_top * u, 0.13 * u, (hy - stem_top) * u))
    if double:
        beam = QPainterPath()
        beam.moveTo(0.38 * u, -1.6 * u)
        beam.lineTo(1.66 * u, -1.78 * u)
        beam.lineTo(1.66 * u, -1.45 * u)
        beam.lineTo(0.38 * u, -1.27 * u)
        beam.closeSubpath()
        path.addPath(beam)
    else:
        flag = QPainterPath()
        flag.moveTo(0.38 * u, -1.6 * u)
        flag.cubicTo(0.55 * u, -1.25 * u, 1.1 * u, -1.15 * u, 1.0 * u, -0.5 * u)
        flag.cubicTo(0.85 * u, -0.95 * u, 0.65 * u, -1.0 * u, 0.51 * u, -1.0 * u)
        flag.closeSubpath()
        path.addPath(flag)
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.setOpacity(alpha)
    edge = QPen(WHITE, 0.2 * u)
    edge.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(edge)
    p.setBrush(WHITE)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


def draw_butterfly(p, x, y, u, color1, color2, flap, angle, alpha):
    """A small cartoon butterfly seen from the front. The wings open and close with `flap`."""
    ws = 0.18 + 0.82 * abs(math.cos(flap))
    upper = QPainterPath()
    upper.moveTo(0.10 * u, -0.10 * u)
    upper.cubicTo(0.25 * u, -1.35 * u, 1.55 * u, -1.55 * u, 1.45 * u, -0.55 * u)
    upper.cubicTo(1.38 * u, -0.05 * u, 0.70 * u, 0.10 * u, 0.10 * u, 0.10 * u)
    lower = QPainterPath()
    lower.moveTo(0.10 * u, 0.05 * u)
    lower.cubicTo(1.00 * u, 0.12 * u, 1.30 * u, 0.90 * u, 0.80 * u, 1.10 * u)
    lower.cubicTo(0.35 * u, 1.25 * u, 0.10 * u, 0.70 * u, 0.10 * u, 0.05 * u)
    wings = []
    for side in (-1, 1):
        tr = QTransform()
        tr.scale(side * ws, 1.0)
        wings.append((tr.map(lower), color2))
        wings.append((tr.map(upper), color1))

    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.setOpacity(alpha)
    p.setBrush(Qt.BrushStyle.NoBrush)
    halo = QPen(WHITE, 0.36 * u)
    halo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    halo.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(halo)
    for path, _ in wings:
        p.drawPath(path)
    edge = QPen(DARK, 0.11 * u)
    edge.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(edge)
    for path, col in wings:
        p.setBrush(col)
        p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    for side in (-1, 1):
        p.drawEllipse(QPointF(side * ws * 0.88 * u, -0.72 * u), 0.2 * u * max(ws, 0.3), 0.2 * u)
    feel = QPen(DARK, 0.07 * u)
    feel.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(feel)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for side in (-1, 1):
        ant = QPainterPath()
        ant.moveTo(0.0, -0.55 * u)
        ant.quadTo(side * 0.12 * u, -1.0 * u, side * 0.42 * u, -1.08 * u)
        p.drawPath(ant)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(DARK)
    p.drawEllipse(QPointF(0, 0.08 * u), 0.13 * u, 0.58 * u)
    p.drawEllipse(QPointF(0, -0.58 * u), 0.15 * u, 0.15 * u)
    p.restore()


def draw_heart(p, x, y, size, color, alpha):
    p.save()
    p.translate(x, y)
    p.scale(size / 200.0, size / 200.0)
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    path = QPainterPath()
    path.moveTo(0, 92)
    path.cubicTo(-160, -18, -88, -118, 0, -38)
    path.cubicTo(88, -118, 160, -18, 0, 92)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    p.restore()


def make_pen(color, width):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_paw(p, x, y, s, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(x, y + 0.25 * s), 0.52 * s, 0.40 * s)
    for dx, dy in ((-0.66, -0.26), (-0.23, -0.64), (0.23, -0.64), (0.66, -0.26)):
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), 0.20 * s, 0.27 * s)


def make_fish_shape():
    """All the pieces of the fish (head points right, to +x), in picture pixels around (0, 0)."""
    P = {}
    body = QPainterPath()
    body.moveTo(455, 20)
    body.cubicTo(415, -55, 320, -125, 160, -152)
    body.cubicTo(-10, -178, -170, -118, -290, -42)
    body.lineTo(-300, -28)
    body.lineTo(-300, 28)
    body.cubicTo(-175, 118, -20, 180, 150, 165)
    body.cubicTo(320, 150, 418, 95, 455, 20)
    body.closeSubpath()
    P["body"] = body

    tail = QPainterPath()                      # deeply forked tail
    tail.moveTo(-285, -26)
    tail.lineTo(-492, -208)
    tail.cubicTo(-335, -70, -335, 70, -492, 208)
    tail.lineTo(-285, 26)
    tail.closeSubpath()
    P["tail"] = tail

    dorsal = QPainterPath()
    dorsal.moveTo(150, -125)
    dorsal.cubicTo(112, -240, 30, -296, -96, -312)
    dorsal.cubicTo(-108, -240, -112, -190, -160, -105)
    dorsal.closeSubpath()
    P["dorsal"] = dorsal

    anal = QPainterPath()
    anal.moveTo(-10, 135)
    anal.cubicTo(-55, 210, -130, 250, -214, 266)
    anal.cubicTo(-214, 215, -206, 165, -190, 100)
    anal.closeSubpath()
    P["anal"] = anal

    pect = QPainterPath()
    pect.moveTo(222, 48)
    pect.cubicTo(160, 36, 60, 70, -14, 168)
    pect.cubicTo(90, 168, 196, 138, 236, 84)
    pect.closeSubpath()
    P["pect"] = pect

    def fan(items):
        rays = QPainterPath()
        for x0, y0, x1, y1 in items:
            rays.moveTo(x0, y0)
            rays.lineTo(x1, y1)
        return rays

    P["tail_rays"] = fan([(-295, 0, -370 - 118 * abs(2 * f / 8.0 - 1.0) ** 1.2 * 1.0, -205 + 410 * f / 8.0)
                          for f in range(0, 9)])
    P["dorsal_rays"] = fan([(125 - 52 * f, -130 + 4 * f, 60 - 30 * f - 8 * f, -285 + 22 * f) for f in range(0, 6)])
    P["anal_rays"] = fan([(-5 - 38 * f, 138 - 4 * f, -80 - 24 * f, 232 + 6 * f) for f in range(0, 5)])
    P["pect_rays"] = fan([(205, 62 + 6 * f, 40 - 10 * f, 118 + 12 * f) for f in range(0, 4)])

    scales = QPainterPath()
    row = 0
    for y in range(-118, 166, 34):
        off = 0 if row % 2 == 0 else 22
        for x in range(-270 + off, 236, 44):
            scales.moveTo(x - 17, y - 8)
            scales.quadTo(x, y + 20, x + 17, y - 8)
        row += 1
    P["scales"] = scales

    stripes = QPainterPath()
    for x in range(-250, 230, 58):
        stripes.moveTo(x, -190)
        stripes.cubicTo(x + 26, -150, x - 24, -112, x + 8, -62)
    P["stripes"] = stripes

    gill = QPainterPath()
    gill.moveTo(268, -142)
    gill.cubicTo(222, -62, 222, 70, 268, 152)
    P["gill"] = gill

    lateral = QPainterPath()
    lateral.moveTo(-292, -4)
    lateral.cubicTo(-110, -26, 100, -30, 240, -8)
    P["lateral"] = lateral

    sheen = QPainterPath()
    sheen.moveTo(-230, -92)
    sheen.cubicTo(-60, -156, 120, -146, 262, -98)
    P["sheen"] = sheen

    bones = QPainterPath()                     # spine, ribs and tail rays
    bones.moveTo(-300, 0)
    bones.lineTo(330, 0)
    for x in range(-190, 300, 58):
        hh = 108.0 * max(0.25, 1.0 - abs(x - 70) / 400.0)
        for sg in (-1, 1):
            bones.moveTo(x, 0)
            bones.quadTo(x - 16, sg * hh * 0.62, x - 50, sg * hh)
    for yy in (-170, -95, 95, 170):
        bones.moveTo(-300, 0)
        bones.lineTo(-462, yy)
    P["bones"] = bones

    skull = QPainterPath()
    skull.moveTo(292, -78)
    skull.cubicTo(370, -78, 428, -36, 440, 12)
    skull.cubicTo(420, 46, 360, 74, 292, 80)
    skull.cubicTo(262, 40, 262, -40, 292, -78)
    skull.closeSubpath()
    P["skull"] = skull
    return P


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "PeekingCat"


def startup_command():
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            exe = w
    return '"%s" "%s"' % (exe, os.path.abspath(__file__))


def autostart_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled):
    if winreg is None:
        return
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TAIL = 14                      # height of the little speech-bubble tail
SHADOW = 14                    # soft shadow margin around the bubble
BUBBLE_BG = QColor(255, 251, 245)
BUBBLE_BORDER = QColor(236, 198, 166)
ACCENT_REMIND = QColor(255, 143, 92)
ACCENT_ASK = QColor(84, 138, 235)
FONT_STACK = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'

BUBBLE_STYLE = """
QLabel { color: #2b2622; font-family: @FONT@; }
QLabel#title { font-size: 15px; }
QLabel#note { color: #8a7a6a; font-size: 11px; }
QPlainTextEdit { background: #ffffff; color: #2b2622; border: 1px solid #ead3bd;
                 border-radius: 10px; padding: 6px; font-size: 13px; font-family: @FONT@; }
QPlainTextEdit:focus { border: 1px solid #ff9d6e; }
QPushButton { background: #fff0e3; color: #2b2622; border: 1px solid #ecc6a6;
              border-radius: 11px; padding: 6px 14px; font-size: 13px; font-family: @FONT@; }
QPushButton:hover { background: #ffe2cc; }
QPushButton:pressed { background: #ffd2b3; }
QPushButton::menu-indicator { image: none; width: 0px; }
QPushButton#primary { background: #ff8f5c; border: 1px solid #f0763d; color: white; font-weight: bold; }
QPushButton#primary:hover { background: #ff7f45; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { background: #e4c7ad; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
""".replace("@FONT@", FONT_STACK)

WINDOW_STYLE = """
QDialog { background: #fffaf3; }
QLabel { color: #2b2622; font-family: @FONT@; font-size: 13px; }
QLabel#h1 { font-size: 18px; font-weight: bold; }
QLabel#hint { color: #8a7a6a; font-size: 11px; }
QLineEdit { background: white; color: #2b2622; border: 1px solid #ead3bd; border-radius: 9px;
            padding: 7px 10px; font-size: 13px; }
QLineEdit:focus { border: 1px solid #ff9d6e; }
QListWidget { background: white; color: #2b2622; border: 1px solid #ead3bd; border-radius: 10px;
              padding: 4px; font-size: 13px; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; }
QListWidget::item:selected { background: #ffe3cf; color: #2b2622; }
QPushButton { background: #fff0e3; color: #2b2622; border: 1px solid #ecc6a6;
              border-radius: 10px; padding: 6px 14px; font-size: 13px; }
QPushButton:hover { background: #ffe2cc; }
QPushButton:pressed { background: #ffd2b3; }
QPushButton#primary { background: #ff8f5c; border: 1px solid #f0763d; color: white; font-weight: bold; }
QPushButton#primary:hover { background: #ff7f45; }
""".replace("@FONT@", FONT_STACK)


def data_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def write_json_atomic(path, data, retries=3):
    """Write JSON so that a crash or power cut can never leave a half-written file.
    Windows refuses os.replace() while an antivirus / OneDrive / editor has the target open, so retry
    a few times, and write the reason to cat_error.log if it still fails."""
    tmp = path + ".tmp"
    last = None
    for attempt in range(retries):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            return True
        except OSError as err:
            last = err
            time.sleep(0.05 * (attempt + 1))
    log_error("could not save %s: %r" % (os.path.basename(path), last))
    return False


LOG_FILE = "cat_error.log"


def log_error(text):
    """Under .pyw there is no console, so problems are written to cat_error.log instead."""
    try:
        with open(data_path(LOG_FILE), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError:
        pass


def install_error_log():
    import traceback

    def hook(kind, value, tb):
        log_error("".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = hook

    def thread_hook(args):                      # pythonw has no stderr, so these used to vanish silently
        name = args.thread.name if args.thread else "?"
        log_error("thread %s:\n%s" % (name, "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))))
    threading.excepthook = thread_hook


def play_chime():
    if not REMINDER_SOUND:
        return
    if winsound is not None:
        try:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            return
        except Exception:
            pass
    QApplication.beep()


# --- meow sound -----------------------------------------------------------
# All cat sounds are made by cat_features.play_cat_sound (no sound files are needed).
MEOW_CHANCE = 0.30            # chance (0 to 1) that the cat meows when it pops up


def cat_sound(kind="random"):
    """Play a cat sound if cat_features.py is there and Meow sounds are on (checked by the caller)."""
    if play_cat_sound is not None:
        play_cat_sound(kind)


def tomorrow_morning():
    now = datetime.now()
    when = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now.hour >= 6 or when <= now:
        when += timedelta(days=1)
    return when


def clean_item(it):
    """Return a safe copy of a reminder read from disk, or None if it is unusable."""
    if not isinstance(it, dict):
        return None
    kind, rep = it.get("kind"), it.get("repeat")
    if kind not in ("remind", "ask") or rep not in ("once", "daily", "days", "interval"):
        return None
    text = str(it.get("text", "")).strip()
    if not text:
        return None
    try:
        due = datetime.fromisoformat(str(it["next"]))
    except (KeyError, ValueError):
        return None
    if due.tzinfo is not None:
        due = due.astimezone().replace(tzinfo=None)
    out = {"kind": kind, "text": text, "repeat": rep,
           "next": due.isoformat(timespec="seconds")}
    if rep == "interval":
        try:
            minutes = int(it.get("minutes", 60))
        except (TypeError, ValueError):
            minutes = 60
        out["minutes"] = min(1440, max(1, minutes))
    if rep in ("daily", "days"):
        try:
            hh, mm = [int(v) for v in str(it["time"]).split(":")]
        except (KeyError, ValueError):
            return None
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        out["time"] = "%02d:%02d" % (hh, mm)
    if rep == "days":
        days = it.get("days")
        if not isinstance(days, list):
            return None
        good = sorted({d for d in days
                       if isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6})
        if not good:
            return None
        out["days"] = good
    if isinstance(it.get("id"), int) and not isinstance(it.get("id"), bool):
        out["id"] = it["id"]
    if isinstance(it.get("src"), str) and it["src"]:
        out["src"] = it["src"][:80]            # marks reminders made by the calendar import
    return out


def compute_next(item, after):
    rep = item.get("repeat")
    if rep == "interval":
        try:
            minutes = int(item.get("minutes", 60))
        except (TypeError, ValueError):
            minutes = 60
        return after + timedelta(minutes=max(1, minutes))
    if rep in ("daily", "days"):
        try:
            hour, minute = [int(v) for v in str(item["time"]).split(":")]
        except (KeyError, ValueError):
            return None
        days = list(range(7)) if rep == "daily" else list(item.get("days", []))
        if not days:
            return None
        for add in range(0, 8):
            try:
                cand = (after + timedelta(days=add)).replace(hour=hour, minute=minute,
                                                             second=0, microsecond=0)
            except ValueError:
                return None
            if cand > after and cand.weekday() in days:
                return cand
    return None


def every_text(minutes):
    if minutes % 60 == 0:
        hours = minutes // 60
        return "every hour" if hours == 1 else "every %d hours" % hours
    return "every %d minutes" % minutes


def describe(item):
    ask = item.get("kind") == "ask"
    rep = item.get("repeat")
    if rep == "interval":
        try:
            when = every_text(int(item.get("minutes", 60)))
        except (TypeError, ValueError):
            when = "repeating"
    elif rep == "daily":
        when = "every day at " + str(item.get("time", ""))
    elif rep == "days":
        days = sorted(d for d in item.get("days", []) if isinstance(d, int) and 0 <= d <= 6)
        names = "every day" if len(days) == 7 else ", ".join(DAY_NAMES[d] for d in days)
        when = "%s at %s" % (names, item.get("time", ""))
    else:
        when = "once"
    try:
        nxt = datetime.fromisoformat(item["next"]).strftime("%a %d %b, %H:%M")
    except Exception:
        nxt = "?"
    return "%s: %s\n%s   \u00b7   next %s" % ("Ask" if ask else "Remind",
                                            item.get("text", ""), when, nxt)


# ----------------------------------------------------------------------
# "Quick add": understands short sentences such as
#   in 20 minutes drink water
#   at 5pm call mom
#   tomorrow at 9 ask what are my top 3 tasks?
#   every weekday at 9:30 stand-up
#   every 45 min stretch
# ----------------------------------------------------------------------
_DT = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
_DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_ASK_PREFIX = re.compile(r"^(?:ask\s+me|ask|question|quiz\s+me)\b\s*[:,\-]?\s*", re.I)
_REMIND_PREFIX = re.compile(r"^(?:remind\s+me|reminder|remind)\b\s*[:,\-]?\s*", re.I)
_EVERY_N = re.compile(r"\bevery\s+(?:(\d+)\s*)?(minutes?|mins?|hours?|hrs?|hr|h|m)\b", re.I)
_EVERY_DAYS = re.compile(r"\b(?:every|each)\s+(weekdays?|weekends?|%s(?:\s*(?:,|and|&)\s*%s)*)"
                         % (_DT, _DT), re.I)
_DAILY = re.compile(r"\b(?:every\s*day|everyday|daily|each\s+day)\b", re.I)
_IN_REL = re.compile(r"\bin\s+(?:(?P<half>half\s+an?\s+hour)|(?P<n>\d+(?:\.\d+)?|an?|one)\s*"
                     r"(?P<u>seconds?|secs?|minutes?|mins?|hours?|hrs?|hr|h|days?|weeks?|m))\b", re.I)
_TOMORROW = re.compile(r"\btomorrow\b", re.I)
_TODAY = re.compile(r"\b(today|tonight)\b", re.I)
_ON_DAY = re.compile(r"\b(on|next)\s+(%s)" % _DT, re.I)
_TIME = re.compile(r"""
      (?:\bat\s+)?\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap])\.?m\.?(?![a-z])
    | \bat\s+(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?(?![\d:])
    | \b(?P<h3>\d{1,2}):(?P<m3>\d{2})(?!\d)
    | \b(?:at\s+)?(?P<word>noon|midnight)\b
""", re.I | re.X)
QUICK_HELP = ("Try:  in 20 minutes drink water   |   at 5pm call mom   |   "
              "tomorrow at 9 ask what are my top 3 tasks?   |   every weekday at 9:30 stand-up   |   "
              "every 45 min stretch.   Use am/pm if you want to be exact.")


def _cut(s, m):
    return (s[:m.start()] + " " + s[m.end():]).strip()


def _hour_candidates(h, m, ap, word):
    """Possible (hour, minute) readings of a spoken time, most likely first."""
    if word:
        return [(12, 0)] if word.lower() == "noon" else [(0, 0)]
    if m > 59:
        raise ValueError("Minutes must be between 0 and 59.")
    if ap:
        if not 1 <= h <= 12:
            raise ValueError("With am/pm the hour must be 1 to 12.")
        return [((h % 12) + (12 if ap.lower() == "p" else 0), m)]
    if h > 23:
        raise ValueError("The hour must be between 0 and 23.")
    if h == 0 or h >= 13:
        return [(h, m)]
    if h == 12:
        return [(12, m), (0, m)]
    if h <= 6:
        return [(h + 12, m), (h, m)]
    return [(h, m), (h + 12, m)]


def _find_time(s):
    m = _TIME.search(s)
    if not m:
        return None, None
    g = m.groupdict()
    if g["h"] is not None:
        cands = _hour_candidates(int(g["h"]), int(g["m"] or 0), g["ap"], None)
    elif g["h2"] is not None:
        cands = _hour_candidates(int(g["h2"]), int(g["m2"] or 0), None, None)
    elif g["h3"] is not None:
        cands = _hour_candidates(int(g["h3"]), int(g["m3"]), None, None)
    else:
        cands = _hour_candidates(0, 0, None, g["word"])
    return cands, m


def parse_quick(text, now=None):
    """Turn a short sentence into a reminder.  Returns (item, None) or (None, error)."""
    now_exact = now or datetime.now()
    now = now_exact.replace(second=0, microsecond=0)
    s = " ".join(str(text).split())
    if not s:
        return None, "Type what the cat should say, and when."

    kind, explicit = "remind", False
    m = _ASK_PREFIX.match(s)
    if m:
        kind, explicit, s = "ask", True, s[m.end():]
    else:
        m = _REMIND_PREFIX.match(s)
        if m:
            explicit, s = True, s[m.end():]
    s = _WEEKDAY_BEFORE_TIME.sub(r"on \1", s, count=1)

    item = None
    when = None
    try:
        m = _EVERY_N.search(s)
        if m:
            minutes = int(m.group(1) or 1) * (60 if m.group(2).lower().startswith("h") else 1)
            if not 1 <= minutes <= 1440:
                return None, "Repeat between every 1 minute and every 24 hours."
            s = _cut(s, m)
            item = {"repeat": "interval", "minutes": minutes}
            when = now_exact.replace(microsecond=0) + timedelta(minutes=minutes)
        else:
            m = _EVERY_DAYS.search(s)
            if m:
                spec = m.group(1).lower()
                if spec.startswith("weekday"):
                    days = [0, 1, 2, 3, 4]
                elif spec.startswith("weekend"):
                    days = [5, 6]
                else:
                    days = sorted({_DAY_INDEX[w[:3]] for w in re.findall(r"[a-z]+", spec)
                                   if w[:3] in _DAY_INDEX and w != "and"})
                s = _cut(s, m)
                item = {"repeat": "days", "days": days}
            else:
                m = _DAILY.search(s)
                if m:
                    s = _cut(s, m)
                    item = {"repeat": "daily"}

        if item is not None and item["repeat"] in ("daily", "days"):
            cands, tm = _find_time(s)
            if cands is None:
                return None, "Add a time, for example: every day at 9:00 ..."
            s = _cut(s, tm)
            item["time"] = "%02d:%02d" % cands[0]
            when = compute_next(item, now_exact)
        elif item is None:
            item = {"repeat": "once"}
            m = _IN_REL.search(s)
            if m:
                if m.group("half"):
                    delta = timedelta(minutes=30)
                else:
                    raw = m.group("n").lower()
                    n = 1.0 if raw in ("a", "an", "one") else float(raw)
                    unit = m.group("u").lower()
                    if unit.startswith("s"):
                        delta = timedelta(seconds=n)
                    elif unit.startswith("h"):
                        delta = timedelta(hours=n)
                    elif unit.startswith("d"):
                        delta = timedelta(days=n)
                    elif unit.startswith("w"):
                        delta = timedelta(weeks=n)
                    else:
                        delta = timedelta(minutes=n)
                if delta < timedelta(seconds=5) or delta > timedelta(days=365):
                    return None, "Pick a time between a few seconds and a year from now."
                s = _cut(s, m)
                when = (now_exact + delta).replace(microsecond=0)
            else:
                day, default_time = None, None
                m = _TOMORROW.search(s)
                if m:
                    day = now.date() + timedelta(days=1)
                    s = _cut(s, m)
                else:
                    m = _ON_DAY.search(s)
                    if m:
                        target = _DAY_INDEX[m.group(2).lower()[:3]]
                        ahead = (target - now.weekday()) % 7
                        if ahead == 0 and m.group(1).lower() == "next":
                            ahead = 7
                        day = now.date() + timedelta(days=ahead)
                        s = _cut(s, m)
                    else:
                        m = _TODAY.search(s)
                        if m:
                            day = now.date()
                            if m.group(1).lower() == "tonight":
                                default_time = [(20, 0)]
                            s = _cut(s, m)
                cands, tm = _find_time(s)
                if cands is not None:
                    s = _cut(s, tm)
                elif day is not None:
                    cands = default_time or [(9, 0)]
                else:
                    return None, "I could not find a time. " + QUICK_HELP
                options = []
                if day is not None:
                    options = [datetime(day.year, day.month, day.day, h, mi) for h, mi in cands]
                    future = [d for d in options if d > now_exact]
                    when = future[0] if future else None
                    if when is None:
                        return None, "That time has already passed."
                else:
                    for add in (0, 1):
                        base = now.date() + timedelta(days=add)
                        options += [datetime(base.year, base.month, base.day, h, mi)
                                    for h, mi in cands]
                    when = min(d for d in options if d > now_exact)
    except ValueError as err:
        return None, str(err)

    if when is None:
        return None, "I could not work out when. " + QUICK_HELP

    msg = re.sub(r"\s+", " ", s).strip(" ,.;:-")
    for _ in range(3):
        before = msg
        if _ASK_PREFIX.match(msg):               # "tomorrow at 9 ask me what I ate"
            msg = _ASK_PREFIX.sub("", msg, count=1)
            kind, explicit = "ask", True
        elif _REMIND_PREFIX.match(msg):
            msg = _REMIND_PREFIX.sub("", msg, count=1)
            explicit = True
        msg = re.sub(r"^(?:to|that|about|please)\s+", "", msg, flags=re.I).strip(" ,.;:-")
        if msg == before:
            break
    if not msg:
        return None, "What should the cat say? Add the message too."
    msg = msg[0].upper() + msg[1:]
    if not explicit and msg.endswith("?"):
        kind = "ask"
    item.update({"kind": kind, "text": msg, "next": when.isoformat(timespec="seconds")})
    return item, None


# a weekday that is directly followed by a time ("friday at 8pm") -> "on friday at 8pm"
_WEEKDAY_BEFORE_TIME = re.compile(
    r"(?<!on )(?<!next )(?<!every )(?<!each )(?<!and )(?<!, )(?<!& )\b(%s)(?=\s+(?:at\s+)?(?:\d|noon|midnight))" % _DT, re.I)
_WEEKDAY_WORD = re.compile(r"(?<!on )(?<!next )(?<!every )(?<!each )(?<!and )(?<!, )(?<!& )\b(%s)" % _DT, re.I)


def parse_tool_reminder(message, when, now=None):
    """The AI tool gives the message and the time separately ("submit lab", "friday at 8pm").
    Returns (item, None) or (None, error)."""
    now = now or datetime.now()
    message = " ".join(str(message).split()).strip(" .")
    when = " ".join(str(when).split()).strip(" .")
    if not message or not when:
        return None, "I need what to remind you about, and when."
    try:                                            # "2026-11-05 20:00" or "2026-11-05T20:00"
        exact = datetime.fromisoformat(when)
        if len(when) <= 10:
            exact = exact.replace(hour=9, minute=0)
        if exact.tzinfo is not None:
            exact = exact.astimezone().replace(tzinfo=None)
        if exact <= now:
            return None, "That time has already passed."
        return {"kind": "remind", "repeat": "once", "text": message[0].upper() + message[1:],
                "next": exact.replace(second=0, microsecond=0).isoformat(timespec="seconds")}, None
    except ValueError:
        pass
    when = re.sub(r"\bthis\s+(?=%s)" % _DT, "on ", when, flags=re.I)        # "this friday" -> "on friday"
    when = _WEEKDAY_WORD.sub(r"on \1", when)                               # "friday at 8" -> "on friday at 8"
    first_err = None
    for text in ("%s %s" % (when, message), "%s %s" % (message, when)):
        item, err = parse_quick(text, now)
        if item is not None:
            return item, None
        first_err = first_err or err
    return None, "I could not understand the time '%s'. Try: in 20 minutes, at 5pm, tomorrow at 9, " \
                 "friday at 8pm or every weekday at 9:30." % when


def when_words(item):
    """'on Fri 06 Nov at 20:00', 'every weekday at 09:30', ... for the cat's answer."""
    rep = item.get("repeat")
    if rep == "interval":
        return every_text(int(item.get("minutes", 60)))
    if rep == "daily":
        return "every day at %s" % item.get("time", "")
    if rep == "days":
        days = sorted(item.get("days", []))
        if days == [0, 1, 2, 3, 4]:
            names = "every weekday"
        elif days == [5, 6]:
            names = "every weekend day"
        else:
            names = "every " + ", ".join(DAY_NAMES[d] for d in days)
        return "%s at %s" % (names, item.get("time", ""))
    try:
        due = datetime.fromisoformat(item["next"])
    except Exception:
        return "soon"
    today = datetime.now().date()
    if due.date() == today:
        day = "today"
    elif due.date() == today + timedelta(days=1):
        day = "tomorrow"
    else:
        day = "on " + due.strftime("%a %d %b")
    return "%s at %s" % (day, due.strftime("%H:%M"))


def _match_subject(subjects, name):
    """Find a study subject by a loose name: exact, start, part, or initials ("DS" = Data Structures)."""
    want = " ".join(name.lower().split())
    if not want:
        return None
    for test in (lambda s: s == want, lambda s: s.startswith(want), lambda s: want in s or s in want,
                 lambda s: "".join(w[0] for w in s.split()) == want.replace(" ", "")):
        for sub in subjects:
            if test(" ".join(sub["name"].lower().split())):
                return sub
    return None


class AnswerBox(QPlainTextEdit):
    def __init__(self, on_submit):
        super().__init__()
        self.on_submit = on_submit

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.on_submit()
            return
        super().keyPressEvent(event)


class Bubble(QWidget):
    """The cat's speech bubble: fades in, types its message, has a soft shadow."""

    def __init__(self, assistant):
        super().__init__()
        self.a = assistant
        self.mode = "remind"
        self.tail_x = 60
        self.accent = ACCENT_REMIND
        self.closing = False
        self.full_text = ""
        self.type_pos = 0
        self.type_step = 1
        self.typing_seconds = 0.0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(BUBBLE_STYLE)
        self.setFixedWidth(BUBBLE_WIDTH + 2 * SHADOW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16 + SHADOW, 12 + SHADOW, 16 + SHADOW, 12 + TAIL + SHADOW)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.badge = QLabel()
        self.stamp = QLabel()
        self.stamp.setObjectName("note")
        head.addWidget(self.badge)
        head.addStretch()
        head.addWidget(self.stamp)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.title)
        self.title.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        self.note = QLabel()
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.box = AnswerBox(lambda: self.a.submit_answer())
        self.box.setPlaceholderText("Click here and type.  Enter = save,  Shift+Enter = new line")
        self.box.setFixedHeight(72)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.b_ok = QPushButton()
        self.b_ok.setObjectName("primary")
        self.b_later = QPushButton()
        menu = QMenu(self.b_later)
        for label, minutes in SNOOZE_CHOICES:
            menu.addAction(label).triggered.connect(
                lambda checked=False, m=minutes: self.a.snooze(minutes=m))
        menu.addSeparator()
        menu.addAction("Tomorrow morning").triggered.connect(
            lambda checked=False: self.a.snooze(tomorrow=True))
        self.b_later.setMenu(menu)
        self.b_skip = QPushButton("Skip")
        self.b_ok.clicked.connect(lambda checked=False: self.on_ok())
        self.b_skip.clicked.connect(lambda checked=False: self.a.dismiss())
        row.addWidget(self.b_ok)
        row.addWidget(self.b_later)
        row.addWidget(self.b_skip)
        row.addStretch()
        lay.addLayout(head)
        lay.addWidget(self.scroll)
        lay.addWidget(self.note)
        lay.addWidget(self.box)
        lay.addLayout(row)

        self.type_timer = QTimer(self)
        self.type_timer.timeout.connect(self.type_tick)
        self.stream_timer = QTimer(self)             # batches streamed AI text (max ~16 redraws/second)
        self.stream_timer.setSingleShot(True)
        self.stream_timer.timeout.connect(self._flush_stream)
        self._stream_text = ""
        self.anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.anim.finished.connect(self.anim_done)

    MAX_BODY_H = 230              # the text area scrolls beyond this height

    def on_ok(self):
        if self.mode == "ask":
            self.a.submit_answer()
        else:
            self.a.dismiss()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.a.on_escape()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self.type_timer.stop()
        self.stream_timer.stop()
        super().hideEvent(event)

    def type_tick(self):
        self.type_pos = min(len(self.full_text), self.type_pos + self.type_step)
        self.title.setText(self.full_text[:self.type_pos])
        if self.type_pos >= len(self.full_text):
            self.type_timer.stop()

    def _fit(self):
        """Resize the text area and the whole bubble for the text currently in self.title."""
        inner = self.width() - 2 * (16 + SHADOW)
        w = max(100, inner - 10)                      # a little room for the scroll bar
        self.title.setFixedWidth(w)
        th = max(self.title.heightForWidth(w), self.title.fontMetrics().height())
        self.title.setFixedHeight(th)
        self.scroll.setFixedHeight(min(th, self.MAX_BODY_H) + 2)
        lay = self.layout()
        lay.activate()
        h = lay.totalHeightForWidth(self.width())
        if h < 0:
            h = lay.sizeHint().height()
        if h != self.height():
            self.setFixedHeight(h)

    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_note(self, text):
        self.note.setText(text)
        self.note.setVisible(bool(text))
        self._fit()
        self.a.place_bubble()

    def _begin_typing(self, text):
        """Size the bubble for the whole message first, then 'type' it in."""
        self.type_timer.stop()
        self.stream_timer.stop()
        self.full_text = text
        self.title.setText(text)
        self._fit()
        self.scroll.verticalScrollBar().setValue(0)
        self.type_step = max(1, int(math.ceil(len(text) / 40.0)))
        self.type_pos = 0
        self.title.setText("")
        self.typing_seconds = (len(text) / float(self.type_step)) * TYPE_SPEED_MS / 1000.0
        self.type_timer.start(TYPE_SPEED_MS)

    def show_text(self, text):
        """Replace the bubble text and type it in."""
        self._begin_typing(text)
        self.a.place_bubble()

    def show_status(self, text):
        """Replace the bubble text at once (no typing): 'Thinking...', errors."""
        self.type_timer.stop()
        self.stream_timer.stop()
        self.full_text = text
        self.title.setText(text)
        self._fit()
        self.scroll.verticalScrollBar().setValue(0)
        self.a.place_bubble()

    def stream_text(self, text, now=False):
        """Show an answer that is still being written (or just finished). Redraws are batched."""
        self.type_timer.stop()
        self.full_text = text
        self._stream_text = text
        if now:
            self.stream_timer.stop()
            self._flush_stream()
        elif not self.stream_timer.isActive():
            self.stream_timer.start(60)

    def _flush_stream(self):
        self.title.setText(self._stream_text)
        self._fit()
        self.a.place_bubble()
        QTimer.singleShot(0, self._scroll_bottom)

    def fade_in(self):
        self.closing = False
        self.anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        force_topmost(self)
        self.anim.setDuration(170)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def fade_out(self):
        if not self.isVisible() or self.closing:
            return
        self.closing = True
        self.type_timer.stop()
        self.anim.stop()
        self.anim.setDuration(130)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.start()

    def anim_done(self):
        if self.closing:
            self.closing = False
            self.hide()
            self.setWindowOpacity(1.0)

    def present(self, item, late, focus=False):
        kind = item.get("kind", "remind")
        chat = bool(item.get("chat"))
        self.mode = "ask" if (kind == "ask" or chat) else "remind"
        self.a.chat_token += 1                    # answers meant for an earlier bubble are ignored now

        if chat:
            self.accent, badge = ACCENT_ASK, "CAT CHAT"
        elif kind == "ask":
            self.accent, badge = ACCENT_ASK, "QUESTION"
        else:
            self.accent, badge = ACCENT_REMIND, "REMINDER"
        self.badge.setText(badge)
        self.badge.setStyleSheet("color: %s; font-size: 10px; font-weight: bold;"
                                 % self.accent.name())
        self.stamp.setText(datetime.now().strftime("%H:%M"))

        if late.total_seconds() > 120:
            due = datetime.now() - late
            self.note.setText("(this was due at %s)" % due.strftime("%H:%M"))
            self.note.show()
        else:
            self.note.setText("")
            self.note.hide()

        self.box.clear()
        self.box.setVisible(self.mode == "ask")
        self.box.setPlaceholderText(
            "Ask me anything.  Enter = send,  Shift+Enter = new line" if chat else
            "Type your answer.  Enter = send,  Shift+Enter = new line")
        self.b_ok.setText("Send" if self.mode == "ask" else "Done")
        self.b_later.setText("Later \u25be")
        self.b_later.setVisible(not chat)
        self.b_skip.setText("Close" if chat else "Skip")
        self.b_skip.setVisible(True)

        steal = (focus or ASK_STEALS_FOCUS) and self.mode == "ask"
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not steal)

        self._begin_typing(str(item.get("text", "")))
        self.a.place_bubble()
        self.fade_in()
        if steal:
            self.activateWindow()
            self.box.setFocus()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(SHADOW, SHADOW, self.width() - 2.0 * SHADOW,
                      self.height() - 2.0 * SHADOW - TAIL)

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

        p.setPen(Qt.PenStyle.NoPen)
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


class ReminderList(QListWidget):
    def __init__(self, on_delete):
        super().__init__()
        self.on_delete = on_delete

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.on_delete()
            return
        super().keyPressEvent(event)


class ReminderWindow(QDialog):
    def __init__(self, assistant):
        super().__init__()
        self.a = assistant
        self.setWindowTitle("Cat assistant - reminders")
        self.setMinimumWidth(600)
        self.setStyleSheet(WINDOW_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)

        title = QLabel("Your cat assistant")
        title.setObjectName("h1")
        root.addWidget(title)

        root.addWidget(QLabel("Tell the cat what and when, then press Enter:"))
        qrow = QHBoxLayout()
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("e.g.  in 20 minutes drink water      or      "
                                      "every day at 9:00 what are my top 3 tasks?")
        self.quick.returnPressed.connect(self.quick_clicked)
        b_quick = QPushButton("Add")
        b_quick.setObjectName("primary")
        b_quick.clicked.connect(lambda checked=False: self.quick_clicked())
        qrow.addWidget(self.quick, 1)
        qrow.addWidget(b_quick)
        root.addLayout(qrow)
        hint = QLabel(QUICK_HELP)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.hide()
        root.addWidget(self.status)

        root.addWidget(QLabel("Coming up (soonest first):"))
        self.list = ReminderList(lambda: self.delete_selected())
        self.list.setMinimumHeight(170)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda item: self.preview_selected())
        root.addWidget(self.list)
        row = QHBoxLayout()
        b_del = QPushButton("Delete selected")
        b_del.clicked.connect(lambda checked=False: self.delete_selected())
        b_now = QPushButton("Show it now")
        b_now.clicked.connect(lambda checked=False: self.preview_selected())
        self.b_adv = QPushButton("Set up step by step \u25be")
        self.b_adv.clicked.connect(lambda checked=False: self.toggle_advanced())
        row.addWidget(b_del)
        row.addWidget(b_now)
        row.addStretch()
        row.addWidget(self.b_adv)
        root.addLayout(row)

        self.adv = QWidget()
        adv_lay = QVBoxLayout(self.adv)
        adv_lay.setContentsMargins(0, 4, 0, 0)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        adv_lay.addWidget(line)

        self.kind = QComboBox()
        self.kind.addItem("Remind me  (the cat says something)", "remind")
        self.kind.addItem("Ask me a question  (I type an answer, the cat replies)", "ask")
        self.text = QLineEdit()
        self.text.setPlaceholderText("e.g.  Drink water      or      What are your top 3 tasks today?")
        self.repeat = QComboBox()
        for label, key in [("Once", "once"), ("Every day", "daily"),
                           ("On selected days", "days"), ("Every few minutes", "interval")]:
            self.repeat.addItem(label, key)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd d MMM yyyy")
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 1440)
        self.minutes.setValue(60)
        self.minutes.setSuffix(" minutes")
        days_box = QWidget()
        dl = QHBoxLayout(days_box)
        dl.setContentsMargins(0, 0, 0, 0)
        self.day_boxes = []
        for name in DAY_NAMES:
            cb = QCheckBox(name)
            cb.setChecked(True)
            dl.addWidget(cb)
            self.day_boxes.append(cb)

        form = QFormLayout()
        self.rows = {}
        for key, label, widget in [("kind", "Type:", self.kind), ("text", "Text:", self.text),
                                   ("repeat", "How often:", self.repeat),
                                   ("date", "Date:", self.date_edit),
                                   ("time", "Time:", self.time_edit),
                                   ("minutes", "Every:", self.minutes),
                                   ("days", "Days:", days_box)]:
            lab = QLabel(label)
            form.addRow(lab, widget)
            self.rows[key] = (lab, widget)
        adv_lay.addLayout(form)
        b_add = QPushButton("Add")
        b_add.setObjectName("primary")
        b_add.clicked.connect(lambda checked=False: self.add_clicked())
        adv_lay.addWidget(b_add)
        root.addWidget(self.adv)
        self.adv.hide()

        self.repeat.currentIndexChanged.connect(lambda i: self.update_rows())
        self.reset_defaults()
        self.update_rows()
        self.refresh()

    def reset_defaults(self):
        soon = datetime.now() + timedelta(minutes=10)
        self.date_edit.setDate(QDate(soon.year, soon.month, soon.day))
        self.time_edit.setTime(QTime(soon.hour, soon.minute))

    def toggle_advanced(self):
        show = not self.adv.isVisible()
        self.adv.setVisible(show)
        self.b_adv.setText("Hide step by step \u25b4" if show else "Set up step by step \u25be")
        self.adjustSize()

    def update_rows(self):
        rep = self.repeat.currentData()
        show = {"date": rep == "once", "time": rep in ("once", "daily", "days"),
                "minutes": rep == "interval", "days": rep == "days"}
        for key, on in show.items():
            for w in self.rows[key]:
                w.setVisible(on)
        self.adjustSize()

    def set_status(self, text, ok):
        self.status.setStyleSheet("color: %s;" % ("#2e8b57" if ok else "#c0392b"))
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def refresh(self):
        keep = self.selected_id()
        self.list.clear()
        for it in self.a.items:
            row = QListWidgetItem(describe(it))
            row.setData(Qt.ItemDataRole.UserRole, it["id"])
            self.list.addItem(row)
            if it["id"] == keep:
                self.list.setCurrentItem(row)
        if not self.a.items:
            empty = QListWidgetItem("Nothing yet. Add your first reminder above.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)

    def selected_id(self):
        row = self.list.currentItem()
        return row.data(Qt.ItemDataRole.UserRole) if row is not None else None

    def delete_selected(self):
        item_id = self.selected_id()
        if item_id is not None:
            self.a.delete(item_id)

    def preview_selected(self):
        item_id = self.selected_id()
        if item_id is not None:
            self.a.preview(item_id)

    def quick_clicked(self):
        item, err = parse_quick(self.quick.text())
        if err:
            self.set_status(err, False)
            return
        item["id"] = self.a.new_id()
        self.a.add_item(item)
        self.quick.clear()
        self.set_status("Added  -  " + describe(item).replace("\n", "  "), True)

    def add_clicked(self):
        text = self.text.text().strip()
        if not text:
            QMessageBox.information(self, "Cat assistant",
                                    "Please type what the cat should say or ask.")
            return
        rep = self.repeat.currentData()
        t = self.time_edit.time()
        now = datetime.now()
        item = {"id": self.a.new_id(), "kind": self.kind.currentData(),
                "text": text, "repeat": rep}
        if rep == "once":
            d = self.date_edit.date()
            when = datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())
            if when <= now:
                QMessageBox.information(self, "Cat assistant",
                                        "That time has already passed. Pick a later time.")
                return
        else:
            if rep in ("daily", "days"):
                item["time"] = "%02d:%02d" % (t.hour(), t.minute())
            if rep == "days":
                days = [i for i, cb in enumerate(self.day_boxes) if cb.isChecked()]
                if not days:
                    QMessageBox.information(self, "Cat assistant", "Tick at least one day.")
                    return
                item["days"] = days
            if rep == "interval":
                item["minutes"] = self.minutes.value()
            when = compute_next(item, now)
            if when is None:
                return
        item["next"] = when.isoformat(timespec="seconds")
        self.a.add_item(item)
        self.text.clear()
        self.set_status("Added  -  " + describe(item).replace("\n", "  "), True)


class Assistant:
    def __init__(self, cat):
        self.cat = cat
        self.items = self.load_items()
        self.queue = []
        self.pending_once = set()           # ids of one-time reminders that are due and waiting to be shown
        self.current = None
        self.window = None
        self.dnd = bool(cat.saved.get("dnd", False))
        self.bubble = Bubble(self)
        self.rps = GameManager(self)
        self.chat_token = 0                 # bumped whenever the bubble shows something new
        model = cat.saved.get("ai_model")
        self.ai = LocalAIAssistant(model_name=model if isinstance(model, str) and model else DEFAULT_MODEL,
                                   history_file=data_path(CHAT_HISTORY_FILE), tool_handler=self.run_tool)
        self.timer = QTimer(cat)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        QTimer.singleShot(1500, self.check)

    def busy(self):
        return self.bubble.isVisible() and not self.bubble.closing

    def new_id(self):
        used = {it.get("id") for it in self.items}
        n = int(time.time() * 1000)
        while n in used:
            n += 1
        return n

    def load_items(self):
        path = data_path(REMINDERS_FILE)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("unexpected layout")
            raw = data.get("items", [])
            if not isinstance(raw, list):
                raise ValueError("unexpected layout")
        except Exception:
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
            return []
        good, used = [], set()
        for n, it in enumerate(raw):
            clean = clean_item(it)
            if clean is None:
                continue
            item_id = clean.get("id")
            if item_id is None or item_id in used:
                item_id = int(time.time() * 1000) + n
                while item_id in used:
                    item_id += 1
            clean["id"] = item_id
            used.add(item_id)
            good.append(clean)
        good.sort(key=lambda it: it["next"])
        return good

    def save_items(self):
        write_json_atomic(data_path(REMINDERS_FILE), {"items": self.items})

    def refresh_window(self):
        if self.window is not None:
            self.window.refresh()
        self.update_tooltip()

    def add_item(self, item):
        self.items.append(item)
        self.items.sort(key=lambda it: it["next"])
        self.save_items()
        self.refresh_window()

    def delete(self, item_id):
        self.items = [it for it in self.items if it.get("id") != item_id]
        if item_id in self.pending_once:               # it was waiting to be shown: drop it from the queue too
            self.pending_once.discard(item_id)
            self.queue = [(q, late) for q, late in self.queue
                          if q.get("id") != item_id or q.get("preview")]
        self.save_items()
        self.refresh_window()

    def preview(self, item_id):
        for it in self.items:
            if it.get("id") == item_id:
                shown = dict(it)
                shown["preview"] = True                # showing a preview must not use up the reminder
                self.queue.insert(0, (shown, timedelta(0)))
                self.show_next(force=True)             # "Show it now" works even in Do not disturb
                return

    def check(self):
        if self.dnd:
            return        # Do not disturb: due reminders stay saved and come when it is switched off
        now = datetime.now()
        changed = False
        for it in list(self.items):
            try:
                due = datetime.fromisoformat(it["next"])
            except Exception:
                self.items.remove(it)
                changed = True
                continue
            if due <= now:
                item_id = it.get("id")
                if it.get("repeat") == "once":
                    # A one-time reminder stays in reminders.json until it is really shown, so it is
                    # not lost if the program is closed while it waits behind another bubble.
                    if item_id not in self.pending_once:
                        self.pending_once.add(item_id)
                        self.queue.append((dict(it), now - due))
                    continue
                if not any(q.get("id") == item_id and not q.get("preview") for q, _ in self.queue):
                    self.queue.append((dict(it), now - due))
                nxt = compute_next(it, now)
                if nxt is None:
                    self.items.remove(it)
                else:
                    it["next"] = nxt.isoformat(timespec="seconds")
                changed = True
        if changed:
            self.items.sort(key=lambda it: it["next"])
            self.save_items()
            self.refresh_window()
        self.show_next()

    def show_next(self, force=False):
        if (self.dnd and not force) or not self.queue or self.bubble.isVisible():
            return
        item, late = self.queue.pop(0)
        item_id = item.get("id")
        if not item.get("preview") and item_id in self.pending_once:
            self.pending_once.discard(item_id)         # shown now: a one-time reminder is used up
            before = len(self.items)
            self.items = [it for it in self.items if it.get("id") != item_id]
            if len(self.items) != before:
                self.save_items()
                self.refresh_window()
        self.current = item
        now = time.perf_counter()
        self.cat.timed["happy"] = now + 0.8
        play_chime()
        self.cat.notify("Peeking Cat - %s" % ("question" if item.get("kind") == "ask" else "reminder"),
                        str(item.get("text", "")))
        self.bubble.present(item, late)
        self.cat.talking_until = now + 0.5 + self.bubble.typing_seconds

    def dismiss(self):
        self.chat_token += 1
        self.ai.cancel()
        self.bubble.fade_out()
        self.current = None
        self.cat.talking_until = 0.0
        QTimer.singleShot(500, self.show_next)

    def on_escape(self):
        """Esc: first stop a running AI answer; otherwise close / snooze the bubble."""
        if self.ai.busy:
            self.chat_token += 1
            self.ai.cancel()
            self.cat.talking_until = 0.0
            self.bubble.show_status("(stopped)  Type something else, or close me.")
            return
        if self.bubble.mode == "ask":
            self.snooze()
        else:
            self.dismiss()

    def snooze(self, minutes=None, tomorrow=False):
        it = self.current
        if it is not None and it.get("chat"):
            self.dismiss()
            return
        if it is not None:
            if tomorrow:
                when = tomorrow_morning()
            else:
                if minutes is None:
                    minutes = ASK_LATER_MINUTES if it.get("kind") == "ask" else SNOOZE_MINUTES
                when = datetime.now() + timedelta(minutes=minutes)
            self.add_item({"id": self.new_id(), "kind": it.get("kind", "remind"),
                           "text": it.get("text", ""), "repeat": "once",
                           "next": when.isoformat(timespec="seconds")})
        self.dismiss()

    def submit_answer(self, shown=None, allow_tools=True):
        """Send what is in the answer box. shown = shorter text for the "You:" line."""
        it = self.current
        answer = self.bubble.box.toPlainText().strip()
        if not answer:
            self.bubble.box.setFocus()
            return
        if it is None or it.get("kind") != "ask":
            self.dismiss()
            return
        if self.ai.busy:
            self.bubble.set_note("Please wait, I am still answering.  Esc = stop")
            return

        token = self.chat_token
        question = "" if it.get("chat") else str(it.get("text", ""))
        shown = (shown or answer).replace("\n", " ")
        self.bubble.set_note("You: " + (shown if len(shown) <= 90 else shown[:87] + "..."))
        self.bubble.box.clear()
        self.bubble.show_status("Thinking .")
        started = self.ai.ask_async(
            prompt=answer,
            context=question or None,
            allow_tools=allow_tools,
            on_chunk=lambda text, t=token: self.on_ai_chunk(t, text),
            on_complete=lambda full, t=token: self.on_ai_done(t, full),
            on_error=lambda err, t=token, a=answer: self.on_ai_error(t, a, err))
        if started:
            QTimer.singleShot(450, lambda t=token: self.think_tick(t, 1))
        else:
            self.bubble.box.setPlainText(answer)      # nothing was sent: keep what the user typed

    def _bubble_is(self, token):
        """True while the bubble still shows the conversation this answer belongs to."""
        return token == self.chat_token and self.bubble.isVisible() and not self.bubble.closing

    def think_tick(self, token, n):
        """Animated 'Thinking . .. ...' while we wait for the first words of the answer."""
        if not (self._bubble_is(token) and self.ai.busy and not self.ai.partial):
            return                                        # the answer started (or was stopped): stop animating
        text = "Thinking " + "." * (n % 3 + 1)
        if n >= 18:                                       # about 8 seconds: the model is probably loading
            text += "\n\nLoading the AI model, please wait.  (Esc = stop)"
        self.bubble.show_status(text)
        QTimer.singleShot(450, lambda t=token, k=n + 1: self.think_tick(t, k))

    def on_ai_chunk(self, token, text):
        if not self._bubble_is(token):
            return
        self.bubble.stream_text(clean_reply(text))
        self.cat.talking_until = time.perf_counter() + 0.8

    def on_ai_done(self, token, reply):
        if self.ai.model_name != self.cat.saved.get("ai_model"):
            self.cat.saved["ai_model"] = self.ai.model_name    # remember the model that really worked
            self.cat.save_settings()
        if not self._bubble_is(token):
            return
        self.bubble.stream_text(reply, now=True)
        self.cat.talking_until = time.perf_counter() + 0.5
        self.bubble.box.setFocus()                     # ready for the next message

    def on_ai_error(self, token, answer, err):
        if not self._bubble_is(token):
            return
        self.bubble.show_status("Oops: %s" % err)
        self.bubble.box.setPlainText(answer)           # so you can just press Enter to try again
        self.bubble.box.moveCursor(QTextCursor.MoveOperation.End)
        self.cat.talking_until = 0.0

    def chat_now(self):
        """Open a chat bubble right now (tray menu)."""
        cur = self.current
        if self.bubble.isVisible() and not self.bubble.closing:
            if cur is not None and cur.get("chat"):
                self.bubble.activateWindow()
                self.bubble.box.setFocus()
                return
            if cur is not None:                        # a reminder is showing: bring it back after the chat
                self.queue.insert(0, (dict(cur), timedelta(0)))
            self.ai.cancel()
        item = {"id": self.new_id(), "kind": "ask", "chat": True,
                "text": "Hi! Ask me anything \U0001F63A", "repeat": "once",
                "next": datetime.now().isoformat(timespec="seconds")}
        self.current = item
        now = time.perf_counter()
        self.cat.timed["happy"] = now + 0.8
        self.cat.wake()
        self.bubble.present(item, timedelta(0), focus=True)
        self.cat.talking_until = now + 0.5 + self.bubble.typing_seconds

    def new_conversation(self):
        """Tray > "Delete chat history": erase the saved chat. Any answer still on its way is dropped."""
        self.chat_token += 1
        self.ai.reset()
        if self.current is not None and self.bubble.isVisible():
            if self.current.get("chat"):
                self.bubble.set_note("")
                self.bubble.show_status("Chat history deleted. What would you like to talk about?")
                self.bubble.box.clear()

    def open_window(self):
        if self.window is None:
            self.window = ReminderWindow(self)
        self.window.reset_defaults()
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def ask_about_text(self, text, question):
        """Screen reader: open the chat and ask the cat about text from the screen."""
        if len(text) > 6000:
            text = text[:6000] + "\n[...]"
        self.chat_now()
        if self.ai.busy:                    # an older answer is still coming: stop it, this question is newer
            self.chat_token += 1
            self.ai.cancel()
            self.cat.talking_until = 0.0
        self.bubble.box.setPlainText('I copied this text from my screen:\n"""\n%s\n"""\n%s' % (text, question))
        self.submit_answer(shown="%s  (about the text from the screen)" % question, allow_tools=False)

    # -- things the AI can do (tool calls). Each returns (ok, what the cat says) ----------
    def run_tool(self, name, args):
        f = self.cat.features
        if name == "add_reminder":
            item, err = parse_tool_reminder(args.get("message") or args.get("text") or "",
                                            args.get("when") or args.get("time") or "")
            if err:
                return False, err
            item["id"] = self.new_id()
            self.add_item(item)
            return True, "Okay! I will remind you %s: %s" % (when_words(item), item["text"])
        if name == "start_timer":
            try:
                minutes = int(round(float(args.get("minutes"))))
            except (TypeError, ValueError):
                return False, "How many minutes should the timer run?"
            if not 1 <= minutes <= 1440:
                return False, "A timer can run from 1 minute to 24 hours."
            replaced = self.cat.timer_sys.end is not None
            self.cat.timer_sys.start(minutes)
            what = "1 minute" if minutes == 1 else "%d minutes" % minutes
            return True, "Timer started: %s.%s I will tell you when the time is up." % (
                what, " (The old timer was replaced.)" if replaced else "")
        if f is None:
            return False, "To-do and study need cat_features.py in the same folder."
        if name == "add_todo":
            text = " ".join(str(args.get("text") or args.get("task") or "").split())
            if not text:
                return False, "What should I put on your to-do list?"
            due_word = " ".join(str(args.get("due") or "").lower().split()).strip(" .")
            due_word = re.sub(r"^(?:on|by|this|next|until)\s+", "", due_word)   # "by friday" -> "friday"
            m = re.fullmatch(r"in\s+(\d{1,3})\s+days?", due_word)
            if m:
                due_word = "+%sd" % m.group(1)
            due = parse_date_word(due_word.replace(" ", "")) if due_word else None
            f.todo.add(text, due)
            f.todo_changed()
            if f.todo_window is not None and f.todo_window.isVisible():
                f.todo_window.refresh()
            msg = "Added to your to-do list: %s" % text
            if due is not None:
                msg += " (due %s)" % due.strftime("%a %d %b")
            elif due_word:
                msg += " (I did not understand the day '%s', so it has no due date)" % due_word
            return True, msg
        if name == "log_study":
            name_ = " ".join(str(args.get("subject") or "").split())
            try:
                minutes = int(round(float(args.get("minutes"))))
            except (TypeError, ValueError):
                return False, "How many minutes did you study?"
            if not name_:
                return False, "Which subject did you study?"
            if not 1 <= minutes <= 720:
                return False, "Please log between 1 and 720 minutes."
            sub = _match_subject(f.study.subjects, name_)
            new = sub is None
            if new:
                sub = f.study.add(name_[0].upper() + name_[1:], None, 30)
            f.log_study(sub["id"], minutes)
            today = f.study.minutes_on(sub, datetime.now().date())
            return True, "Logged %d min of %s%s. Today: %d of %d min." % (
                minutes, sub["name"], " (new subject)" if new else "", today, sub["goal"])
        return False, "I don't know how to do that yet."

    def set_dnd(self, value):
        self.dnd = bool(value)
        self.cat.saved["dnd"] = self.dnd
        self.cat.save_settings()
        if not self.dnd:
            self.show_next()
        self.update_tooltip()

    def update_tooltip(self):
        tray = getattr(self.cat, "tray", None)
        if tray is None:
            return
        tip = "Peeking Cat"
        if self.dnd:
            tip += "  (do not disturb)"
        ts = getattr(self.cat, "timer_sys", None)
        if ts is not None and ts.end is not None:
            tip += "\nTimer: " + ts.text()
        if self.items:
            try:
                when = datetime.fromisoformat(self.items[0]["next"]).strftime("%a %H:%M")
                text = str(self.items[0].get("text", ""))
                if len(text) > 40:
                    text = text[:37] + "..."
                tip += "\nNext: %s  -  %s" % (text, when)
            except Exception:
                pass
        tray.setToolTip(tip)

    def place_bubble(self):
        b, cat = self.bubble, self.cat
        screen = QGuiApplication.primaryScreen()
        a = screen.availableGeometry()
        cat_top = cat.y() + cat.pad + int((1.0 - cat.pos_) * cat.cat_h)
        center = cat.x() + cat.width() // 2
        x = max(a.x() - SHADOW + 8,
                min(center - b.width() // 2, a.x() + a.width() - b.width() + SHADOW - 8))
        y = max(a.y() - SHADOW, cat_top + 6 - (b.height() - SHADOW))
        tail = max(SHADOW + 28, min(center - x, b.width() - SHADOW - 28))
        if (x, y) != (b.x(), b.y()):
            b.move(x, y)
        if tail != b.tail_x:
            b.tail_x = tail
            b.update()


TIMER_SHOW_SECONDS = 6.0       # when a timer starts, the cat stays out this long to show it


class TimerBubble(QWidget):
    """A small speech bubble above the cat that shows the time left on the timer."""

    def __init__(self):
        super().__init__()
        self.tail_x = 60
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(BUBBLE_STYLE)
        self.setFixedWidth(210 + 2 * SHADOW)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16 + SHADOW, 12 + SHADOW, 16 + SHADOW, 12 + TAIL + SHADOW)
        lay.setSpacing(2)
        self.badge = QLabel("TIMER")
        self.badge.setStyleSheet("color: %s; font-size: 10px; font-weight: bold;"
                                 % ACCENT_REMIND.name())
        self.big = QLabel()
        self.big.setStyleSheet("font-size: 28px; font-weight: bold; color: #2b2622;")
        self.note = QLabel()
        self.note.setObjectName("note")
        lay.addWidget(self.badge)
        lay.addWidget(self.big)
        lay.addWidget(self.note)
        lay.activate()
        self.setFixedHeight(lay.sizeHint().height())

    def set_text(self, big, note):
        if self.big.text() != big:
            self.big.setText(big)
        if self.note.text() != note:
            self.note.setText(note)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(SHADOW, SHADOW, self.width() - 2.0 * SHADOW,
                      self.height() - 2.0 * SHADOW - TAIL)
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
        p.setBrush(ACCENT_REMIND)
        p.drawRect(QRectF(body.left(), body.top(), body.width(), 4))
        p.restore()
        p.setPen(QPen(BUBBLE_BORDER, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class CatTimer:
    """A simple countdown timer. When it ends, the cat pops up and tells you.
    The end time is saved in settings.json, so the timer survives a restart.
    While it runs, a bubble above the cat shows the time left whenever the cat is out."""

    PRESETS = [("1 minute", 1), ("5 minutes", 5), ("10 minutes", 10), ("15 minutes", 15),
               ("25 minutes (focus)", 25), ("30 minutes", 30), ("45 minutes", 45),
               ("1 hour", 60), ("2 hours", 120)]

    def __init__(self, cat):
        self.cat = cat
        self.end = None
        self.minutes = 0
        data = cat.saved.get("timer")
        if isinstance(data, dict):
            try:
                self.end = float(data["end"])
                self.minutes = int(data.get("minutes", 0))
            except (KeyError, TypeError, ValueError):
                self.end, self.minutes = None, 0
        self.pinned_until = 0.0
        self.bubble = TimerBubble()
        self.qt = QTimer(cat)
        self.qt.setInterval(1000)
        self.qt.timeout.connect(self.check)
        self.qt.start()

    def update_bubble(self):
        """Called every frame by the cat: show the time left while the cat is out."""
        cat = self.cat
        b = self.bubble
        show = (self.end is not None and cat.pos_ > 0.5 and not cat.assistant.busy())
        if not show:
            if b.isVisible():
                b.hide()
            return
        b.set_text(self.text(), "left of %s" % ("1 minute" if self.minutes == 1
                                                 else "%d minutes" % self.minutes)
                   if self.minutes else "left")
        screen = QGuiApplication.primaryScreen()
        a = screen.availableGeometry()
        cat_top = cat.y() + cat.pad + int((1.0 - cat.pos_) * cat.cat_h)
        center = cat.x() + cat.width() // 2
        x = max(a.x() - SHADOW + 8,
                min(center - b.width() // 2, a.x() + a.width() - b.width() + SHADOW - 8))
        y = max(a.y() - SHADOW, cat_top + 6 - (b.height() - SHADOW))
        tail = max(SHADOW + 28, min(center - x, b.width() - SHADOW - 28))
        if (x, y) != (b.x(), b.y()):
            b.move(x, y)
        if tail != b.tail_x:
            b.tail_x = tail
            b.update()
        if not b.isVisible():
            b.show()
            b.raise_()
            force_topmost(b)
        elif cat.ticks % 20 == 0:
            force_topmost(b)

    def remaining(self):
        if self.end is None:
            return None
        return max(0, int(math.ceil(self.end - time.time())))

    def text(self):
        left = self.remaining()
        if left is None:
            return "No timer running"
        h, rest = divmod(left, 3600)
        m, s = divmod(rest, 60)
        return "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)

    def save(self):
        if self.end is None:
            self.cat.saved.pop("timer", None)
        else:
            self.cat.saved["timer"] = {"end": round(self.end, 1), "minutes": self.minutes}
        self.cat.save_settings()

    def start(self, minutes):
        minutes = int(max(1, min(1440, minutes)))
        self.minutes = minutes
        self.end = time.time() + minutes * 60
        self.pinned_until = time.perf_counter() + TIMER_SHOW_SECONDS
        if self.cat.features is not None:
            self.cat.features.on_timer_started(minutes)
        self.save()
        self.refresh()
        self.cat.wake()

    def cancel(self):
        self.end = None
        if self.cat.features is not None:
            self.cat.features.on_timer_cancelled()
        self.save()
        self.refresh()

    def ask_custom(self):
        from PySide6.QtWidgets import QInputDialog
        minutes, ok = QInputDialog.getInt(None, "Timer", "Minutes:", 25, 1, 1440)
        if ok:
            self.start(minutes)

    def refresh(self):
        self.update_menu()
        self.cat.assistant.update_tooltip()

    def update_menu(self):
        status = getattr(self.cat, "timer_status_action", None)
        cancel = getattr(self.cat, "timer_cancel_action", None)
        if status is not None:
            status.setText("Timer: " + self.text() if self.end is not None else "No timer running")
        if cancel is not None:
            cancel.setEnabled(self.end is not None)

    def check(self):
        if self.end is None:
            return
        late = time.time() - self.end
        if late >= 0:
            minutes = self.minutes
            self.end = None
            self.save()
            if self.cat.features is not None:
                self.cat.features.on_timer_done(minutes)
            what = "1 minute" if minutes == 1 else "%d minutes" % minutes
            text = "Time's up! Your %s timer is done." % what if minutes else "Time's up!"
            item = {"id": -1, "kind": "remind", "text": text, "repeat": "once"}
            self.cat.assistant.queue.append((item, timedelta(seconds=late)))
            self.cat.assistant.show_next()
            self.refresh()
        else:
            self.update_menu()
            self.cat.assistant.update_tooltip()


class PeekingCat(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app

        # Not "transparent for input": cat_motion.py lets clicks pass through everywhere except
        # on the cat's body, so you can pick the cat up.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.saved = self.read_settings()

        self.pos_slider = None
        self.pos_label = None
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_settings)
        try:
            self.cat_w = int(self.saved.get("width", CAT_WIDTH))
        except (TypeError, ValueError):
            self.cat_w = CAT_WIDTH
        try:
            self.x_frac = min(1.0, max(0.0, float(self.saved.get("x_frac", 1.0))))
        except (TypeError, ValueError):
            self.x_frac = 1.0

        self.mouth = MOUTH_DEFAULT
        self.mouth_cover = MOUTH_COVER
        self.big_mode = False          # True while the Cat Arcade shows the huge cat
        self.size_before_big = None
        self.walk_offset = 0.0         # sideways stroll distance in pixels (cat_features.py)
        self.features = None
        self.weather = None
        self.kitten = None
        self.youtube = None
        self.notes = None
        self.screen_reader = None
        self.mover = CatMover(self)    # pick up / throw / sit on windows (cat_motion.py)
        self.load_cat()

        self.pos_ = 0.0
        self.vel = 0.0
        self.target = 0.0
        self.eye = [[0.0, 0.0], [0.0, 0.0]]
        self.closure = 0.0
        self.blink_start = None
        self.next_blink = time.perf_counter() + random.uniform(*BLINK_EVERY)
        self.paused = False
        self.anchor = QCursor.pos()
        self.last_move = 0.0
        self.last_t = time.perf_counter()
        self.ticks = 0

        mood = self.saved.get("mood", "auto")
        self.mood = mood if mood in [k for _, k in MOODS] else "auto"
        self.emotion = "normal"
        self.emo_changed = 0.0
        self.pop = 0.0
        self.timed = {}
        self.prev_cur = QCursor.pos()
        self.speed = 0.0
        self.agitation = 0.0
        self.hover = 0.0
        self.last_surprise = 0.0
        self.low_battery = False
        self.battery_checked = -999.0
        self.hidden_since = time.perf_counter() - 30.0
        self.reversals = []
        self.last_dir = 0
        self.idle_plan = None
        self.talking_until = 0.0
        self.feed = None             # {"kind": "fish"/"milk", "start": time} while the cat eats
        self.full_until = 0.0
        self.fish_shape = make_fish_shape()

        self.reposition()
        self.show()
        force_topmost(self)
        self.assistant = Assistant(self)
        self.timer_sys = CatTimer(self)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.features = self._start_part("cat_features", lambda: CatFeatures(self, base_dir, WINDOW_STYLE,
                                                                             compute_next), CatFeatures)
        self.notes = self._start_part("notes", lambda: NotesManager(base_dir, WINDOW_STYLE, self), NotesManager)
        self.screen_reader = self._start_part("screen_ocr", lambda: ScreenReader(self.assistant.ask_about_text,
                                                                                 WINDOW_STYLE), ScreenReader)
        self.weather = self._start_part("weather", lambda: WeatherService(self), WeatherService)
        self.kitten = self._start_part("kitten", lambda: Kitten(self, cat_sound), Kitten)
        self.youtube = self._start_part("youtube", lambda: YouTubeService(self, base_dir, WINDOW_STYLE),
                                        YouTubeService)

        self.make_tray()

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.app.primaryScreenChanged.connect(lambda screen: self.apply_size(self.cat_w))

    def _start_part(self, name, make, available):
        """Start one optional part. A broken part is logged and left out; the cat keeps working."""
        if available is None:
            return None
        try:
            return make()
        except Exception as err:
            log_error("%s could not start: %r" % (name, err))
            return None

    def set_temp_mood(self, key):
        """Change the mood without saving it, and tick it in the Mood menu."""
        self.mood = key
        group = getattr(self, "mood_group", None)
        if group is not None:
            for act in group.actions():
                if act.data() == key:
                    act.setChecked(True)
        self.wake()

    def notify(self, title, text):
        """A pop-up message from the tray icon. Sounds are no use to a deaf person, so reminders and
        timers are also shown as a Windows notification (switch off: tray > Pop-up notifications)."""
        if not self.saved.get("visual_alerts", True):
            return
        tray = getattr(self, "tray", None)
        try:
            if tray is not None and QSystemTrayIcon.supportsMessages():
                tray.showMessage(title, text[:240], QSystemTrayIcon.MessageIcon.Information, 10000)
        except Exception as err:
            log_error("notify failed: %r" % (err,))

    def set_visual_alerts(self, value):
        self.saved["visual_alerts"] = bool(value)
        self.save_settings()

    def load_cat(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), IMAGE_FILE)
        base = QPixmap(path)
        if base.isNull():
            QMessageBox.critical(None, "Peeking Cat",
                                 "Could not find or open the cat picture:\n\n%s\n\n"
                                 "Put cat.png in the same folder as this program." % path)
            sys.exit(1)
        self.orig = base.copy()      # untouched picture (with eyes), used for the tray icon

        f = base.width() / REF_W
        self.mouth, self.mouth_cover = MOUTH_DEFAULT, MOUTH_COVER
        p = QPainter(base)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(f, f)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FUR)
        for r in COVERS:
            p.drawRoundedRect(r, 60, 60)
        p.end()

        self.base = base
        self.apply_size(self.cat_w)

    def apply_size(self, width):
        if self.big_mode:
            width = int(max(MIN_WIDTH, min(self.big_width(), width)))
        else:
            width = int(max(MIN_WIDTH, min(MAX_WIDTH, width)))
        self.cat_w = width
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        self.cat_h = round(width * self.base.height() / self.base.width())
        self.pad = max(PAD, int(round(self.cat_h * HEADROOM)))
        self.scale_ = width / REF_W
        # extra window height below the edge the cat sits on, so the paws can hang over it
        self.paw_drop = 0 if self.big_mode else int(round(PAW_DROP * self.scale_)) + 2
        self.pix = self.base.scaled(
            int(width * dpr), int(self.cat_h * dpr),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.pix.setDevicePixelRatio(dpr)
        # a copy in screen pixels to test "is the mouse on the cat's body?" (cat_motion.py)
        self.hit_img = self.base.scaled(width, self.cat_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.FastTransformation).toImage()
        self.measure_body()
        self.reposition()
        self.update()

    def measure_body(self):
        """Find the middle of the body where it meets the taskbar edge, and put the two paws at equal
        distances left and right of it. (The face is not exactly above the body: the body leans a little
        to the left, so putting the paws under the eyes made them look shifted to the right.)
        Sets self.paw_mid_px (middle, in screen pixels) and self.paw_cx (the two paw positions, in
        picture units, because draw_paws() draws with the picture scale)."""
        img = self.hit_img
        w, h = img.width(), img.height()
        lo, hi = PAW_BODY_ROWS
        row = int(max(lo, min(hi, SHOW_FRACTION)) * h)

        def solid(x, y):
            return ((img.pixel(x, y) >> 24) & 0xFF) >= BODY_ALPHA

        lefts, rights = [], []
        for y in range(max(0, row - 3), min(h, row + 4)):          # a few rows, so one odd pixel row cannot fool us
            left = next((x for x in range(w) if solid(x, y)), None)
            right = next((x for x in range(w - 1, -1, -1) if solid(x, y)), None)
            if left is not None and right is not None and right > left:
                lefts.append(left)
                rights.append(right)
        if lefts:
            left, right = sum(lefts) / len(lefts), sum(rights) / len(rights)
        else:                                                       # no picture found: the old fixed layout
            left, right = w * 0.5 - 1110.0 * self.scale_, w * 0.5 + 1110.0 * self.scale_
        mid, span = (left + right) / 2.0, (right - left) * PAW_SPREAD
        self.paw_mid_px = mid
        self.paw_cx = [(mid - span) / self.scale_, (mid + span) / self.scale_]

    def big_width(self):
        """Biggest cat width that fits BIG_SCREEN_FRACTION of the screen (height and width)."""
        screen = QGuiApplication.primaryScreen()
        g = screen.geometry()
        ratio = self.base.height() / self.base.width()
        total = ratio * (1.0 + HEADROOM)               # window height = cat_h + pad
        by_height = g.height() * BIG_SCREEN_FRACTION / total
        by_width = g.width() * 0.95
        return int(max(MIN_WIDTH, min(by_height, by_width)))

    def set_big_mode(self, on, width=None):
        """Cat Arcade: a big cat in the middle of the screen. Off: back to the normal size."""
        if on == self.big_mode:
            return
        if on:
            self.mover.go_home()                       # a carried or sitting cat comes home first
            self.size_before_big = self.cat_w
            self.big_mode = True
            self.apply_size(width or self.big_width())
        else:
            self.big_mode = False
            back = self.size_before_big or self.saved.get("width", CAT_WIDTH)
            self.size_before_big = None
            try:
                back = int(back)
            except (TypeError, ValueError):
                back = CAT_WIDTH
            self.apply_size(back)
        self.wake()

    def show_target(self):
        """How far the cat comes out: SHOW_FRACTION at home, the whole cat in the Cat Arcade."""
        return 1.0 if self.big_mode else SHOW_FRACTION

    def rise(self):
        """0..1: how far the cat has come out compared with how far it CAN come out.
        (pos_ alone never reaches 1.0 when SHOW_FRACTION is below 1.0, so fades use this.)"""
        return max(0.0, min(1.0, self.pos_ / max(0.01, self.show_target())))

    def wake(self):
        if not self.paused:
            self.last_move = time.perf_counter()
            self.target = self.show_target()

    def choose_size(self, width):
        if self.big_mode:
            self.size_before_big = int(max(MIN_WIDTH, min(MAX_WIDTH, width)))   # used when the arcade closes
            self.wake()
            return
        self.apply_size(width)
        self.saved["width"] = self.cat_w
        self.save_settings()
        self.wake()

    def choose_mood(self, key):
        self.mood = key
        self.saved["mood"] = key
        self.save_settings()
        self.wake()

    def mood_phase(self, t, period):
        """Where we are (0..1) in a one-shot animation such as a sneeze or yawn.
        In Auto it plays once; when picked from the Mood menu it repeats with a short rest."""
        el = t - self.emo_changed
        if self.mood == "auto":
            return max(0.0, min(1.0, (el - 0.3) / period))      # 0.3 s: let the cat finish rising
        return min(1.0, (el % (period + 1.5)) / period)

    def pick_emotion(self, now):
        carried = self.mover.emotion(now)                  # being carried, falling, landing, napping
        if carried and self.feed is None:
            return carried
        if self.feed is not None:
            fi = self.feed_info(now)
            if fi is None:
                self.feed = None
                self.timed["happy"] = now + 2.0
            elif fi[0] == "arrive":
                return "surprised"
            elif fi[0] == "eat":
                return "eat" if self.feed["kind"] == "fish" else "drink"
            else:
                return "love"
        if self.full_until > now:
            return "sleepy"
        if self.features is not None:
            forced = self.features.forced_emotion(now)      # good night routine
            if forced:
                return forced
        if self.mood != "auto":
            return self.mood
        for name in ("angry", "surprised", "love", "confused", "cry", "emotional", "blush"):
            if self.timed.get(name, 0.0) > now:
                return name
        if self.features is not None:
            walking = self.features.walk_emotion()
            if walking:
                return walking
        if self.low_battery:
            return "sad"
        if self.timed.get("happy", 0.0) > now:
            return "happy"
        if self.talking_until > now:
            return "talk"
        if self.youtube is not None:
            music = self.youtube.music_mood(now)           # while a song plays: sing along / dance to it
            if music:
                return music
        for name in ("dance", "singing", "playful", "sneeze", "yawn"):
            if self.timed.get(name, 0.0) > now:
                return name
        if self.idle_plan and now - self.last_move > IDLE_MOOD_AFTER:
            return self.idle_plan
        if is_night():
            return "sleepy"
        return "normal"

    def new_appearance(self, now):
        if is_night():
            self.idle_plan = "sleeping"
        elif random.random() < WHISTLE_CHANCE:
            self.idle_plan = "whistle"
        else:
            self.idle_plan = None
        roll = random.random()
        yawn_p = YAWN_NIGHT_CHANCE if is_night() else YAWN_CHANCE
        wait = 2.5 if (self.hidden_since is not None
                       and now - self.hidden_since >= HAPPY_AFTER_HIDDEN) else 0.0
        if roll < FUN_CHANCE:
            self.timed[random.choice(("dance", "singing", "playful"))] = now + FUN_STAY_SECONDS
        elif roll < FUN_CHANCE + SNEEZE_CHANCE:
            self.timed["sneeze"] = now + wait + 0.5 + SNEEZE_SECONDS
        elif roll < FUN_CHANCE + SNEEZE_CHANCE + yawn_p:
            self.timed["yawn"] = now + wait + 0.5 + YAWN_SECONDS
        if self.saved.get("meow", True) and random.random() < MEOW_CHANCE:
            QTimer.singleShot(int((wait + 0.35) * 1000), self.do_meow)
        if self.features is not None:
            self.features.maybe_walk(now)

    def do_meow(self):
        """Say 'meow' (sound + moving mouth)."""
        if self.paused or self.pos_ <= 0.0:
            return
        cat_sound("random")                         # meow, mew, chirp, trill or squeak
        self.talking_until = max(self.talking_until, time.perf_counter() + 0.9)

    # -- picked up / petted (called by cat_motion.py) -------------------------------
    def on_cat_clicked(self):
        """A single click on the cat: petting."""
        now = time.perf_counter()
        self.last_move = now
        self.timed["love"] = now + 1.8
        if self.features is not None:
            self.features.on_petted()
        elif self.saved.get("meow", True) and random.random() < 0.4:
            QTimer.singleShot(200, self.do_meow)

    def on_picked_up(self):
        self.last_move = time.perf_counter()
        self.hidden_since = None
        if self.saved.get("meow", True):
            cat_sound("squeak")

    def on_landed(self, on_window):
        now = time.perf_counter()
        self.last_move = now
        self.timed["happy"] = now + 2.0
        if self.saved.get("meow", True) and on_window:
            QTimer.singleShot(250, lambda: cat_sound("chirp"))

    def call_home(self):
        """Tray: bring a carried or sitting cat back to its place on the taskbar."""
        self.mover.go_home()
        self.wake()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.tray_menu.popup(QCursor.pos())
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.mover.press(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        self.mover.move(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mover.release(event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mover.double_click()

    def do_meow_now(self):
        """Tray > Meow now: the cat comes out and meows right away."""
        self.wake()
        QTimer.singleShot(450, self.do_meow)

    def set_meow(self, value):
        self.saved["meow"] = bool(value)
        self.save_settings()

    def update_emotion(self, now, dt, cur, real_dt=None):
        dx_move = cur.x() - self.prev_cur.x()
        inst = math.hypot(dx_move, cur.y() - self.prev_cur.y()) / max(real_dt or dt, 0.008)
        self.prev_cur = cur
        self.speed += (inst - self.speed) * min(1.0, dt * 12.0)

        if self.speed > SHAKE_SPEED:
            self.agitation += dt
        else:
            self.agitation = max(0.0, self.agitation - dt * 0.8)
        if self.agitation > SHAKE_SECONDS:
            self.timed["angry"] = now + 3.0
            self.agitation = 0.0

        if abs(dx_move) >= 3:
            direction = 1 if dx_move > 0 else -1
            if self.last_dir and direction != self.last_dir:
                self.reversals.append(now)
            self.last_dir = direction
        self.reversals = [t0 for t0 in self.reversals if now - t0 < CONFUSE_WINDOW]
        if len(self.reversals) >= CONFUSE_TURNS and self.speed < SHAKE_SPEED:
            self.timed["confused"] = now + 3.0
            self.reversals = []

        if self.speed > SURPRISE_SPEED and now - self.last_surprise > 6.0:
            self.timed["surprised"] = now + 1.4
            self.last_surprise = now

        body_hit = getattr(self.mover, "hit", None)               # the fallback CatMover has no hit()
        on_cat = body_hit(cur) if body_hit is not None else self.geometry().contains(cur)
        if self.pos_ > 0.4 and on_cat:
            self.hover += dt
        else:
            self.hover = 0.0
        if self.hover > 1.0:
            self.timed["love"] = now + 1.5
            if self.features is not None:
                self.features.on_petted()
            if self.hover < 9.0 and not self.paused:
                self.last_move = now

        if now - self.battery_checked > 30.0:
            self.battery_checked = now
            self.low_battery = battery_is_low()

        emo = self.pick_emotion(now)
        if emo != self.emotion:
            self.emotion = emo
            self.emo_changed = now
        self.pop = max(0.0, 1.0 - (now - self.emo_changed) / 0.35)

    def choose_position(self, frac, from_slider=False):
        self.x_frac = min(1.0, max(0.0, frac))
        self.saved["x_frac"] = round(self.x_frac, 3)
        self.save_timer.start()
        self.reposition()
        self.sync_position_slider(from_slider)
        self.wake()

    def sync_position_slider(self, from_slider=False):
        percent = int(round(self.x_frac * 100))
        if self.pos_label is not None:
            self.pos_label.setText("Position: %d%%   (0 = left edge, 100 = right edge)" % percent)
        if self.pos_slider is not None and not from_slider:
            self.pos_slider.blockSignals(True)
            self.pos_slider.setValue(percent)
            self.pos_slider.blockSignals(False)

    def settings_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)

    def read_settings(self):
        path = self.settings_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        try:                                   # broken file: keep a copy before it is overwritten
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass
        log_error("settings.json could not be read; a copy was saved as settings.json.bak")
        return {}

    def save_settings(self):
        write_json_atomic(self.settings_path(), self.saved)
        
    def make_tray(self):
        self.tray = QSystemTrayIcon(self.make_tray_icon(), self.app)
        self.tray.setToolTip("Peeking Cat")
        menu = QMenu()
        menu.setStyleSheet(TRAY_MENU_STYLE)

        def add(target, text, fn):
            act = target.addAction(text)
            act.triggered.connect(lambda checked=False, f=fn: f())
            return act

        add(menu, "Chat with the cat", self.assistant.chat_now)
        if self.screen_reader is not None:
            add(menu, "Read text from screen...", self.screen_reader.start)
        add(menu, "Reminders...", self.assistant.open_window)
        if self.notes is not None:
            notes_menu = menu.addMenu("Sticky notes")
            add(notes_menu, "New note", lambda: self.notes.new_note())
            add(notes_menu, "Notes && search...", self.notes.open_manager)
            add(notes_menu, "Show all notes", self.notes.show_all)
            add(notes_menu, "Hide all notes", self.notes.hide_all)
        if self.features is not None:
            self.features.add_menu(menu, add)

        timer_menu = menu.addMenu("Timer")
        for label, minutes in CatTimer.PRESETS:
            timer_menu.addAction(label).triggered.connect(
                lambda checked=False, m=minutes: self.timer_sys.start(m))
        timer_menu.addAction("Custom...").triggered.connect(
            lambda checked=False: self.timer_sys.ask_custom())
        timer_menu.addSeparator()
        self.timer_status_action = timer_menu.addAction("")
        self.timer_status_action.setEnabled(False)
        self.timer_cancel_action = timer_menu.addAction("Cancel timer")
        self.timer_cancel_action.triggered.connect(
            lambda checked=False: self.timer_sys.cancel())
        timer_menu.aboutToShow.connect(self.timer_sys.update_menu)
        self.timer_sys.update_menu()
        if self.weather is not None:
            self.weather.add_menu(menu, add)
        if self.youtube is not None:
            self.youtube.add_menu(menu, add)
        self.dnd_action = menu.addAction("Do not disturb")
        self.dnd_action.setCheckable(True)
        self.dnd_action.setChecked(self.assistant.dnd)
        self.dnd_action.toggled.connect(self.assistant.set_dnd)
        menu.addSeparator()

        pet_menu = menu.addMenu("Play with the cat")
        add(pet_menu, "Cat Arcade (mini games)", self.assistant.rps.start_game)
        if self.kitten is not None:
            add(pet_menu, "Invite the kitten", lambda: self.kitten.visit(manual=True))
        add(pet_menu, "Call the cat home", self.call_home)
        feed_menu = pet_menu.addMenu("Feed the cat")
        feed_menu.addAction("Fish").triggered.connect(
            lambda checked=False: self.feed_cat("fish"))
        feed_menu.addAction("Milk").triggered.connect(
            lambda checked=False: self.feed_cat("milk"))
        feed_menu.addSeparator()
        self.feed_info_action = feed_menu.addAction("")
        self.feed_info_action.setEnabled(False)
        feed_menu.aboutToShow.connect(self.update_feed_menu)
        self.update_feed_menu()
        mood_menu = pet_menu.addMenu("Mood")
        group = QActionGroup(mood_menu)
        group.setExclusive(True)
        for label, key in MOODS:
            act = mood_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mood == key)
            group.addAction(act)
            act.setData(key)
            act.triggered.connect(lambda checked=False, k=key: self.choose_mood(k))
        self.mood_group = group
        pet_menu.addSeparator()
        self.meow_action = pet_menu.addAction("Meow sounds")
        self.meow_action.setCheckable(True)
        self.meow_action.setChecked(bool(self.saved.get("meow", True)))
        self.meow_action.toggled.connect(self.set_meow)
        self.alerts_action = pet_menu.addAction("Pop-up notifications")
        self.alerts_action.setCheckable(True)
        self.alerts_action.setChecked(bool(self.saved.get("visual_alerts", True)))
        self.alerts_action.toggled.connect(self.set_visual_alerts)
        pickup = pet_menu.addAction("Cat can be picked up")
        pickup.setCheckable(True)
        pickup.setChecked(bool(self.saved.get("pickup", True)))
        pickup.toggled.connect(self.set_pickup)
        if self.kitten is not None:
            visits = pet_menu.addAction("Kitten visits")
            visits.setCheckable(True)
            visits.setChecked(self.kitten.enabled())
            visits.toggled.connect(self.kitten.set_enabled)
        add(pet_menu, "Meow now", self.do_meow_now)
        if self.features is not None:
            self.features.add_pet_menu(pet_menu, add)

        size_menu = menu.addMenu("Cat size")
        for name, w in SIZE_PRESETS:
            size_menu.addAction(name).triggered.connect(
                lambda checked=False, w=w: self.choose_size(w))
        size_menu.addSeparator()
        size_menu.addAction("Bigger").triggered.connect(
            lambda checked=False: self.choose_size(self.cat_w + SIZE_STEP))
        size_menu.addAction("Smaller").triggered.connect(
            lambda checked=False: self.choose_size(self.cat_w - SIZE_STEP))
        pos_menu = menu.addMenu("Cat position")
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(4)
        self.pos_label = QLabel()
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(0, 100)
        self.pos_slider.setMinimumWidth(240)
        self.pos_slider.valueChanged.connect(
            lambda v: self.choose_position(v / 100.0, from_slider=True))
        lay.addWidget(self.pos_label)
        lay.addWidget(self.pos_slider)
        slider_action = QWidgetAction(pos_menu)
        slider_action.setDefaultWidget(box)
        pos_menu.addAction(slider_action)
        pos_menu.addSeparator()
        self.sync_position_slider()
        for name, f in [("Far left", 0.0), ("Left", 0.25), ("Center", 0.5),
                        ("Right", 0.75), ("Far right (near clock)", 1.0)]:
            pos_menu.addAction(name).triggered.connect(
                lambda checked=False, f=f: self.choose_position(f))
        pos_menu.addSeparator()
        pos_menu.addAction("Move left").triggered.connect(
            lambda checked=False: self.choose_position(self.x_frac - POSITION_STEP))
        pos_menu.addAction("Move right").triggered.connect(
            lambda checked=False: self.choose_position(self.x_frac + POSITION_STEP))

        menu.addSeparator()
        if winreg is not None:
            self.auto_action = menu.addAction("Start with Windows")
            self.auto_action.setCheckable(True)
            self.auto_action.setChecked(autostart_enabled())
            self.auto_action.toggled.connect(self.toggle_autostart)
            if self.auto_action.isChecked():
                set_autostart(True)      # refresh the path if the file was moved
        add(menu, "Delete chat history", self.assistant.new_conversation)
        self.pause_action = menu.addAction("Pause cat")
        self.pause_action.setCheckable(True)
        self.pause_action.setChecked(self.paused)
        self.pause_action.toggled.connect(self.set_paused)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(lambda checked=False: self.quit_app())
        for m in [menu] + menu.findChildren(QMenu):
            m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.NoDropShadowWindowHint)
            m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.assistant.update_tooltip()

    def set_pickup(self, value):
        self.saved["pickup"] = bool(value)
        self.save_settings()
        if not value:
            self.mover.go_home()

    def prepare_quit(self, *args):
        """Save everything before the program ends (Quit, or Windows shutting down / signing out)."""
        if self.notes is not None:
            self.notes.prepare_quit()          # open notes stay open for the next start
        if self.youtube is not None:
            self.youtube.shutdown()            # stop the music
        if self.save_timer.isActive():         # a position change from the last 0.4 s
            self.save_timer.stop()
        self.save_settings()

    def quit_app(self):
        self.prepare_quit()
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.hide()                        # no "ghost" icon left near the clock
        self.app.quit()

    def make_tray_icon(self):
        icon = QIcon()
        for size in (16, 24, 32, 48, 64):
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            src = self.orig.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            p = QPainter(pm)
            p.drawPixmap((size - src.width()) // 2, (size - src.height()) // 2, src)
            p.end()
            icon.addPixmap(pm)
        return icon

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.tray_menu.hide()
            self.assistant.open_window()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:       # a normal left click
            self.tray_menu.popup(QCursor.pos())

    def toggle_autostart(self, value):
        set_autostart(value)
        if autostart_enabled() != value:
            QMessageBox.warning(None, "Peeking Cat",
                                "Windows did not allow changing the startup setting.")
            self.auto_action.blockSignals(True)
            self.auto_action.setChecked(not value)
            self.auto_action.blockSignals(False)

    def set_paused(self, value):
        self.paused = value
        if value:
            self.mover.go_home()                   # a paused cat hides behind the taskbar
            self.target = 0.0

    def reposition(self):
        if not self.mover.is_home() and not self.big_mode:
            self.mover.apply()                     # carried / falling / sitting on a window
            return
        screen = QGuiApplication.primaryScreen()
        a = screen.availableGeometry()
        w = self.cat_w
        base_h = self.cat_h + self.pad
        h = base_h + getattr(self, "paw_drop", 0)
        span = max(0, a.width() - w - RIGHT_MARGIN)
        x = a.x() + int(round(span * self.x_frac))
        if self.walk_offset:
            x = max(a.x(), min(x + int(round(self.walk_offset)), a.x() + a.width() - w))
        y = a.y() + a.height() - base_h
        if self.big_mode:
            g = screen.geometry()           # whole screen, so there is no gap above the taskbar
            y = g.y() + g.height() - base_h
        if self.geometry().getRect() != (x, y, w, h):
            self.setGeometry(x, y, w, h)

    def option_windows(self):
        """Visible option windows: Reminders, dialogs, tray menus (not the cat's own overlays)."""
        found = []
        for w in QApplication.topLevelWidgets():
            if w is self or not w.isVisible() or w.isMinimized():
                continue
            if w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
                continue                              # the cat, its bubbles and the timer stay in front
            if w.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Popup):
                found.append(w)
        return found

    def update_stacking(self):
        """Cat goes BEHIND the options while one is open, and back IN FRONT of everything otherwise."""
        opts = self.option_windows()
        if not opts:
            force_topmost(self)
            return
        place_behind(self, lowest_window(opts))

    def update_spring(self, now, dt):
        """At home: decide whether the cat peeks out or hides, and move it smoothly.
        Returns True when the cat is completely hidden (nothing to draw)."""
        stay = IDLE_HIDE_SECONDS
        if self.emotion == "sleeping":
            stay = SLEEP_STAY_SECONDS
        elif self.emotion in ("dance", "singing", "whistle", "playful"):
            stay = FUN_STAY_SECONDS
        if (self.emotion in ("sneeze", "yawn")
                or self.timed.get("sneeze", 0.0) > now or self.timed.get("yawn", 0.0) > now):
            stay = max(stay, ANIM_STAY_SECONDS)
        if now - self.last_move > stay:
            self.target = 0.0
        out = self.show_target()                       # the whole cat in the Arcade (not cut in half)
        if self.big_mode and not self.paused:          # Cat Arcade: stay out so you can see the mood
            self.last_move = now
            self.target = out
        if (self.assistant.busy() or self.feed is not None or self.full_until > now
                or (self.kitten is not None and self.kitten.active())):
            self.last_move = now
            self.target = out
        if self.features is not None and not self.paused and self.features.keep_out():
            self.last_move = now                  # good night, a stroll or a short message: stay out
            self.target = out
        if self.youtube is not None and not self.paused and self.youtube.keep_out():
            self.last_move = now                  # music is playing and the cat sings / dances: stay out
            self.target = out
        if self.timer_sys.end is not None and not self.paused:    # stay out until the timer ends
            self.last_move = now
            self.target = out

        acc = SPRING_K * (self.target - self.pos_) - SPRING_C * self.vel
        self.vel += acc * dt
        self.pos_ += self.vel * dt
        if self.pos_ < 0.0:
            self.pos_, self.vel = 0.0, 0.0
        if self.target > 0.0 and self.pos_ > self.target:
            self.pos_ = self.target
            if self.vel > 0.0:
                self.vel = 0.0
        if self.target == 0.0 and self.pos_ < 0.003 and abs(self.vel) < 0.02:
            was_visible = self.pos_ > 0.0
            self.pos_, self.vel = 0.0, 0.0
            if self.hidden_since is None:
                self.hidden_since = now
            if was_visible:
                self.update()                    # wipe the last frame
            if self.timer.interval() != 40:
                self.timer.setInterval(40)       # idle: use less CPU
            return True
        if self.timer.interval() != 16:
            self.timer.setInterval(16)
        return False


    def tick(self):
        now = time.perf_counter()
        real_dt = now - self.last_t
        dt = min(real_dt, 0.05)
        self.last_t = now
        if dt <= 0:
            return

        self.ticks += 1
        if self.ticks % 120 == 0:
            self.reposition()
        if self.ticks % 6 == 0 and self.pos_ > 0.0:
            self.update_stacking()
        if self.ticks % 6 == 0:                    # a Windows panel is open: the taskbar would cover the paws
            self.panel_open = self.mover.is_home() and system_panel_open()
        if self.assistant.busy():
            if self.ticks % 20 == 0:
                force_topmost(self.assistant.bubble)
            self.assistant.place_bubble()
        self.timer_sys.update_bubble()
        if self.features is not None:
            try:
                self.features.tick(now)
                self._feature_fails = 0
            except Exception:
                self._feature_fails = getattr(self, "_feature_fails", 0) + 1
                if self._feature_fails in (1, 50, 500):            # log it, but do not flood the log
                    log_error("features.tick failed (%d in a row):\n%s" % (self._feature_fails, traceback.format_exc()))
                if self._feature_fails >= 600:                      # ~10 s of failing every frame: give up
                    self.features = None
        self.mover.update_input()                  # only the cat's body catches the mouse
        free = self.mover.tick(dt, now)            # True while carried, falling or sitting on a window

        cur = QCursor.pos()

        if math.hypot(cur.x() - self.anchor.x(), cur.y() - self.anchor.y()) >= MOVE_THRESHOLD:
            self.anchor = cur
            if self.hidden_since is not None:
                self.new_appearance(now)
                if now - self.hidden_since >= HAPPY_AFTER_HIDDEN:
                    self.timed["happy"] = now + 2.5
            self.hidden_since = None
            if not self.paused:
                self.last_move = now
                self.target = self.show_target()

        self.update_emotion(now, dt, cur, real_dt)
        if free:
            if self.timer.interval() != 16:
                self.timer.setInterval(16)
        elif self.update_spring(now, dt):
            return

        s = self.scale_
        top = self.y() + self.pad + (1.0 - self.pos_) * self.cat_h
        k = 1.0 - math.exp(-dt * 16.0)
        for i, (cx, cy) in enumerate(EYES):
            ex = self.x() + cx * s
            ey = top + cy * s
            dx, dy = cur.x() - ex, cur.y() - ey
            dist = math.hypot(dx, dy)
            if dist > 0:
                strength = min(1.0, dist / EYE_RANGE_PX)
                tx = dx / dist * strength * EYE_MAX_X
                ty = dy / dist * strength * EYE_MAX_Y
            else:
                tx = ty = 0.0
            self.eye[i][0] += (tx - self.eye[i][0]) * k
            self.eye[i][1] += (ty - self.eye[i][1]) * k

        if self.blink_start is None and now >= self.next_blink:
            self.blink_start = now
        self.closure = 0.0
        if self.blink_start is not None:
            p = (now - self.blink_start) / BLINK_DURATION
            if p >= 1.0:
                self.blink_start = None
                self.next_blink = now + random.uniform(*BLINK_EVERY)
            else:
                self.closure = 0.5 - 0.5 * math.cos(2.0 * math.pi * p)

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        if self.pos_ <= 0.0:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        s = self.scale_
        t = time.perf_counter()
        top = self.pad + (1.0 - self.pos_) * self.cat_h
        fi = self.feed_info(t)

        p.save()
        # the body is cut at the taskbar edge, so it never shows inside the taskbar
        p.setClipRect(QRectF(0, 0, self.width(), self.pad + self.cat_h))
        mover = self.mover
        if mover.tilt or not mover.is_home():               # dangling while carried, squash on landing
            bottom = self.pad + self.cat_h
            p.translate(self.cat_w / 2.0, bottom - self.cat_h * 0.5)
            p.rotate(mover.tilt)
            p.translate(0, self.cat_h * 0.5)
            p.scale(1.0, mover.squash(t))
            p.translate(-self.cat_w / 2.0, -bottom)
        self.body_motion(p, self.emotion, t, top)
        rain = self.weather is not None and self.weather.umbrella()
        if rain and self.weather.rain_drops():
            self.draw_rain(p, t, top)
        if rain:
            self.draw_umbrella(p, t, top)
        strolling = self.features is not None and self.features.gait() is not None
        if self.emotion == "playful" or strolling:
            self.draw_tail(p, t, top)
        if self.emotion == "playful":
            self.draw_butterflies(p, t, top, behind=True)
        p.drawPixmap(QPointF(0, top), self.pix)

        pop = 1.0 + 0.2 * self.pop
        for i, ((cx, cy), (ox, oy)) in enumerate(zip(EYES, self.eye)):
            p.save()
            p.translate(cx * s, top + cy * s)
            p.scale(s * pop, s * pop)
            self.draw_eye(p, self.emotion, i, ox, oy)
            p.restore()

        if fi is not None and self.feed["kind"] == "milk":
            self.draw_bowl(p, t, top, fi[0], fi[1])       # the bowl goes under the tongue

        if self.emotion in ("whistle", "singing", "blush", "talk", "playful", "eat", "drink",
                             "sneeze", "yawn"):
            self.draw_mouth(p, self.emotion, t, top)

        if fi is not None and self.feed["kind"] == "fish":
            self.draw_fish(p, t, top, fi[0], fi[1])

        if self.emotion == "playful":
            self.draw_butterflies(p, t, top, behind=False)

        if self.emotion == "cry":
            self.draw_tears(p, t, top)

        p.restore()

        if self.mover.paws_visible():
            self.draw_paws(p, t)
        self.draw_symbols(p, self.emotion, t, top)
        if fi is not None and fi[0] == "done":
            self.draw_feed_hearts(p, t, top, fi[1])
        if strolling:
            self.draw_walk_hearts(p, t, top)
        p.end()

    # -- weather: umbrella and rain (weather.py says when) -------------------------------
    UMBRELLA_RED = QColor(255, 104, 112)
    UMBRELLA_CREAM = QColor(255, 244, 230)
    RAIN_COLOR = QColor(80, 150, 255, 215)

    def _canopy(self, cx, rim, half, dome):
        path = QPainterPath()
        path.moveTo(cx - half, rim)
        path.cubicTo(cx - half, rim - dome * 1.25, cx + half, rim - dome * 1.25, cx + half, rim)
        n = 6
        seg = 2.0 * half / n
        for i in range(n):                                   # scalloped lower edge
            x0 = cx + half - i * seg
            path.quadTo(x0 - seg / 2.0, rim - 110, x0 - seg, rim)
        path.closeSubpath()
        return path

    def draw_umbrella(self, p, t, top):
        """A striped umbrella above the head. It is drawn BEHIND the cat picture, so the ears
        overlap its edge and the cat looks like it is sitting under it."""
        cx, rim, half, dome = REF_W / 2.0, 40.0, 1480.0, 640.0
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        p.translate(cx, 1400.0)
        p.rotate(3.0 * math.sin(t * 1.6))                    # held, so it sways a little
        p.translate(-cx, -1400.0)
        apex = rim - dome * 0.94
        p.setPen(make_pen(DARK, 40))                         # the stick
        p.drawLine(QPointF(cx, apex), QPointF(cx, rim + 900))
        canopy = self._canopy(cx, rim, half, dome)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.UMBRELLA_RED)
        p.drawPath(canopy)
        p.save()
        p.setClipPath(canopy)
        p.setBrush(self.UMBRELLA_CREAM)
        n = 6
        seg = 2.0 * half / n
        for k in range(1, n, 2):                             # cream stripes
            x0 = cx - half + k * seg
            wedge = QPainterPath()
            wedge.moveTo(cx, apex - 40)
            wedge.lineTo(x0, rim + 30)
            wedge.lineTo(x0 + seg, rim + 30)
            wedge.closeSubpath()
            p.drawPath(wedge)
        p.setBrush(QColor(255, 255, 255, 70))                # shine
        p.drawEllipse(QPointF(cx - half * 0.45, rim - dome * 0.55), half * 0.22, dome * 0.12)
        p.restore()
        p.setPen(make_pen(DARK, 34))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(canopy)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(DARK)
        p.drawEllipse(QPointF(cx, apex - 30), 46, 46)          # little knob on top
        p.restore()

    def draw_rain(self, p, t, top):
        """Rain drops around the umbrella (they stop on the umbrella)."""
        s = self.scale_
        cx, rim, half, dome = REF_W / 2.0, 40.0, 1480.0, 640.0
        y_top = -top / s
        y_end = self.cat_h / s
        span = y_end - y_top
        p.save()
        p.translate(0, top)
        p.scale(s, s)
        pen = QPen(self.RAIN_COLOR, 28)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for i in range(30):
            x = (i * 397 + 131) % int(REF_W)
            speed = 0.9 + (i * 37 % 10) / 12.0
            y = y_top + ((t * speed + i * 0.137) % 1.0) * span
            dx = x - cx
            if abs(dx) < half:                               # under the umbrella: no rain
                surface = rim - dome * 0.94 * (1.0 - (dx / half) ** 2)
                if y + 110 > surface:
                    continue
            p.drawLine(QPointF(x, y), QPointF(x - 30, y + 110))
        p.restore()

    def draw_paws(self, p, t):
        """Two small, round, cute paws on the top edge of the taskbar: the round paw sits on the
        edge and three round toes hang down over it. They are placed symmetrically around the middle
        of the body at the edge (measure_body) and move with the body (body_xform).
        When the cat strolls, the paws step one after the other (lift, swing forward, put down) in time
        with the little hops of the body. When it dances, the paw on the side the body leans away from
        lifts and swings out while the other one takes the weight."""
        if self.big_mode or getattr(self, "paw_drop", 0) <= 0:
            return
        fade = smooth((self.rise() - 0.3) / 0.5)      # paws appear as the cat rises
        if fade <= 0.0:
            return
        # While a Windows panel (Wi-Fi, volume...) is open, the taskbar covers everything below its
        # top edge. So the paws are lifted up and rest fully ABOVE the edge instead of hanging over it.
        goal = 1.0 if getattr(self, "panel_open", False) else 0.0
        lift_k = getattr(self, "paw_lift", 0.0)
        lift_k += (goal - lift_k) * 0.3
        self.paw_lift = goal if abs(goal - lift_k) < 0.01 else lift_k
        gait = self.features.gait() if self.features is not None else None
        walking = gait is not None and gait["mode"] == "walk"
        dancing = self.emotion == "dance" and not walking
        s = self.scale_
        edge = self.pad + self.cat_h                                # the taskbar edge (window pixels)
        top = self.pad + (1.0 - self.pos_) * self.cat_h
        body = self.body_xform(self.emotion, t, top)                # the same move that the body makes
        if dancing:
            lean, _beat = self.dance_step(t)
        p.save()
        p.translate(0, edge - self.paw_lift * PAW_DROP * s)         # y = 0 is the taskbar edge
        p.scale(s, s)
        p.setOpacity(fade)
        toes = ((-92.0, 52.0), (0.0, 60.0), (92.0, 52.0))          # toe centres, radius 64
        for k, cx in enumerate(getattr(self, "paw_cx", (1250.0, 2360.0))):   # centred on the body (measure_body)
            if body is not None:                                    # the paw stays attached to the body
                cx = body.map(QPointF(cx * s, edge)).x() / s
            lift, swing, tilt, press = 0.0, 0.0, 0.0, 0.0
            if walking:
                g = gait["phase"] + (math.pi if k else 0.0)       # the two paws are half a step apart
                sp = gait["speed"]
                lift = max(0.0, math.sin(g)) * sp * 150.0          # paw goes up ...
                swing = -math.cos(g) * sp * 85.0 * gait["dir"]     # ... and forward, then back down
                tilt = -math.cos(g) * sp * 7.0 * gait["dir"]
            elif dancing:
                side = 1.0 if k else -1.0                          # +1 = right paw, -1 = left paw
                free = max(0.0, side * lean)                       # body leans away: this paw is free ...
                press = max(0.0, -side * lean)                     # ... body leans over it: it carries the weight
                lift = DANCE_PAW_LIFT * free                       # the free paw goes up, out and tilts
                swing = side * DANCE_PAW_SWING * free
                tilt = side * DANCE_PAW_TILT * free
            elif gait is not None:                                 # sitting: tiny breathing bob
                lift = 4.0 * (0.5 + 0.5 * math.sin(t * 2.2 + k))
            p.save()
            p.translate(cx + swing, -lift)
            p.rotate(tilt)
            p.scale(PAW_SCALE * (1.0 + 0.05 * press), PAW_SCALE * (1.0 - 0.07 * press))   # the paw under load squashes
            shape = QPainterPath()
            shape.addEllipse(QPointF(0, -25), 175, 128)                         # round paw
            for dx, ty in toes:
                toe = QPainterPath()
                toe.addEllipse(QPointF(dx, ty), 64, 64)                         # round toes
                shape = shape.united(toe)
            p.setPen(make_pen(DARK, 46))
            p.setBrush(FUR)
            p.drawPath(shape)
            p.setPen(Qt.PenStyle.NoPen)                                         # hide the inner outline
            p.setBrush(FUR)
            p.drawEllipse(QPointF(0, -25), 166, 119)
            for dx, ty in toes:
                p.drawEllipse(QPointF(dx, ty), 56, 56)
            lines = QPainterPath()                                              # small dents between toes
            for dx in (-46.0, 46.0):
                lines.moveTo(dx, 38)
                lines.quadTo(dx + (5.0 if dx < 0 else -5.0), 72, dx, 104)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(make_pen(DARK, 24))
            p.drawPath(lines)
            p.setPen(Qt.PenStyle.NoPen)                                         # tiny pink toe beans
            p.setBrush(QColor(255, 150, 170))
            for dx, ty in toes:
                p.drawEllipse(QPointF(dx, ty + 28), 24, 17)
            p.setBrush(QColor(255, 255, 255, 170))                              # soft shine
            p.drawEllipse(QPointF(-85, -85), 34, 20)
            p.restore()
        p.restore()

    def feed_log(self):
        log = self.saved.get("feed_log")
        out = []
        if isinstance(log, list):
            for entry in log:
                try:
                    ts, kind = float(entry[0]), str(entry[1])
                except Exception:
                    continue
                if kind in FOODS:
                    out.append((ts, kind))
        return out

    def feed_info(self, now):
        """(phase, progress 0..1) while the cat is eating, else None."""
        f = self.feed
        if f is None:
            return None
        el = now - f["start"]
        eat = FISH_EAT_SECONDS if f["kind"] == "fish" else MILK_DRINK_SECONDS
        if el < FEED_ARRIVE_SECONDS:
            return ("arrive", max(0.0, el) / FEED_ARRIVE_SECONDS)
        el -= FEED_ARRIVE_SECONDS
        if el < eat:
            return ("eat", el / eat)
        el -= eat
        if el < FEED_DONE_SECONDS:
            return ("done", el / FEED_DONE_SECONDS)
        return None

    def feed_cat(self, kind):
        if kind not in FOODS:
            return
        now = time.perf_counter()
        if self.feed is not None and self.feed_info(now) is not None:
            return                                   # already eating
        wall = time.time()
        log = self.feed_log()
        recent = [ts for ts, _ in log if 0 <= wall - ts < FEED_LIMIT_MINUTES * 60]
        if len(recent) >= FEED_LIMIT:
            self.full_until = now + 3.0
            self.wake()
            self.tray.showMessage("Peeking Cat", "I'm full right now! Ask me again a bit later.",
                                  QSystemTrayIcon.MessageIcon.NoIcon, 4000)
            return
        log.append((wall, kind))
        self.saved["feed_log"] = [[round(ts, 1), k] for ts, k in log[-FEED_LOG_MAX:]]
        self.save_settings()
        self.feed = {"kind": kind, "start": now}
        self.wake()
        self.update_feed_menu()

    def update_feed_menu(self):
        log = self.feed_log()
        today = datetime.now().date()
        counts = {"fish": 0, "milk": 0}
        for ts, kind in log:
            try:
                if datetime.fromtimestamp(ts).date() == today:
                    counts[kind] += 1
            except (OverflowError, OSError, ValueError):
                pass
        if not log:
            text = "Not fed yet"
        else:
            try:
                last = datetime.fromtimestamp(log[-1][0]).strftime("%H:%M")
            except (OverflowError, OSError, ValueError):
                last = "?"
            text = "Fed today: %d fish, %d milk  (last %s)" % (counts["fish"], counts["milk"], last)
        self.feed_info_action.setText(text)

    @staticmethod
    def fish_eaten(prog):
        """How much of the fish is gone (0..1): bite, chew, bite, chew ..."""
        k = max(0.0, min(1.0, prog)) * FISH_BITES
        i = int(k)
        if i >= FISH_BITES:
            return 1.0
        f = min(1.0, (k - i) / 0.3)
        f = f * f * (3.0 - 2.0 * f)
        return (i + f) / FISH_BITES

    def draw_fish(self, p, t, top, phase, prog):
        mx, my = self.mouth[0], self.mouth[1]
        if phase == "arrive":
            e, dy, alpha = 0.0, -1500.0 * (1.0 - prog) ** 2, 1.0
        elif phase == "eat":
            e, dy, alpha = self.fish_eaten(prog), 0.0, 1.0
        else:
            q = min(1.0, prog / 0.5)
            e, dy, alpha = 1.0, 1100.0 * q * q, 1.0 - q
            if alpha <= 0.0:
                return
        P = self.fish_shape
        x_cut = 450.0 - 900.0 * e          # the fish is eaten from its head (right) end
        chew = math.sin(t * 9.0) if phase == "eat" else 0.0
        flop = math.sin(t * 5.0) * 2.0 if phase == "arrive" else 0.0
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        p.setOpacity(alpha)
        p.translate(mx, my + 130.0 + dy)
        p.rotate(-5.0 + 2.5 * chew + flop)
        p.translate(-x_cut, 0)
        p.setBrush(Qt.BrushStyle.NoBrush)

        bones = P["bones"]
        p.setPen(make_pen(DARK, 34))
        p.drawPath(bones)
        p.setPen(make_pen(BONE_COLOR, 16))
        p.drawPath(bones)
        p.setPen(make_pen(DARK, 24))
        p.setBrush(BONE_COLOR)
        p.drawPath(P["skull"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(DARK)
        p.drawEllipse(QPointF(350, -18), 28, 28)
        p.setBrush(Qt.BrushStyle.NoBrush)

        if e < 0.999:
            clip = QPainterPath()
            clip.addRect(QRectF(-700, -500, x_cut + 730, 1000))
            r = 105.0 * min(1.0, e * 14.0)
            if r > 1.0:
                bite = QPainterPath()
                for by in (-190.0, 0.0, 190.0):
                    bite.addEllipse(QPointF(x_cut + 30.0, by), r, r)
                clip = clip.subtracted(bite)

            def cut(path):
                br = path.boundingRect()
                if br.right() <= x_cut - 80.0:
                    return path
                if br.left() >= x_cut + 30.0:
                    return QPainterPath()
                return path.intersected(clip)

            fin_pen = make_pen(DARK, 22)

            def draw_fin(key, rays_key):
                shp = cut(P[key])
                if shp.isEmpty():
                    return
                fg = QLinearGradient(shp.boundingRect().topLeft(), shp.boundingRect().bottomRight())
                fg.setColorAt(0.0, QColor(255, 176, 96))
                fg.setColorAt(1.0, QColor(255, 118, 62))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(fg))
                p.drawPath(shp)
                p.save()
                p.setClipPath(shp)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(make_pen(FISH_FIN_DARK, 9))
                p.drawPath(P[rays_key])
                p.restore()
                p.setPen(fin_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(shp)

            draw_fin("tail", "tail_rays")
            draw_fin("dorsal", "dorsal_rays")
            draw_fin("anal", "anal_rays")

            body = cut(P["body"])
            if not body.isEmpty():
                g = QLinearGradient(0, -180, 0, 180)
                g.setColorAt(0.0, QColor(26, 84, 136))
                g.setColorAt(0.30, QColor(84, 156, 196))
                g.setColorAt(0.52, QColor(198, 223, 233))
                g.setColorAt(0.74, QColor(246, 232, 222))
                g.setColorAt(1.0, QColor(255, 224, 202))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawPath(body)

                p.save()
                p.setClipPath(body)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(make_pen(QColor(10, 44, 84, 150), 15))
                p.drawPath(P["stripes"])
                p.setPen(make_pen(QColor(255, 255, 255, 80), 6))
                p.drawPath(P["scales"])
                p.setPen(make_pen(QColor(255, 120, 110, 190), 13))
                p.drawPath(P["lateral"])
                p.setPen(make_pen(QColor(255, 255, 255, 120), 22))
                p.drawPath(P["sheen"])
                p.setPen(make_pen(QColor(255, 130, 120, 90), 46))
                p.drawPath(P["gill"].translated(-26, 0))
                p.setPen(make_pen(QColor(40, 40, 40, 200), 11))
                p.drawPath(P["gill"])
                mouth_line = QPainterPath()
                mouth_line.moveTo(456, 24)
                mouth_line.quadTo(420, 40, 384, 30)
                p.setPen(make_pen(DARK, 13))
                p.drawPath(mouth_line)
                p.setPen(make_pen(QColor(255, 196, 70), 9))
                p.setBrush(WHITE)
                p.drawEllipse(QPointF(352, -34), 38, 38)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(DARK)
                p.drawEllipse(QPointF(360, -34), 24, 24)
                p.setBrush(WHITE)
                p.drawEllipse(QPointF(369, -44), 8, 8)
                if e > 0.0005:                       # raw pink flesh along the bitten edge
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(make_pen(FISH_FLESH, 76))
                    p.drawPath(clip)
                    p.setPen(make_pen(FISH_FLESH_LIGHT, 30))
                    p.drawPath(clip)
                p.restore()

                p.setPen(make_pen(DARK, 24))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(body)

            draw_fin("pect", "pect_rays")
        p.restore()

    def draw_milk_bottle(self, p, bx, base_y):
        """A little glass bottle of milk with a heart label, standing next to the bowl."""
        neck_top = base_y - 540.0
        shoulder = base_y - 370.0
        glass = QPainterPath()
        glass.moveTo(bx - 62, neck_top)
        glass.lineTo(bx - 62, neck_top + 70)
        glass.cubicTo(bx - 62, shoulder - 10, bx - 126, shoulder - 20, bx - 126, shoulder + 70)
        glass.lineTo(bx - 126, base_y - 40)
        glass.quadTo(bx - 126, base_y, bx - 86, base_y)
        glass.lineTo(bx + 86, base_y)
        glass.quadTo(bx + 126, base_y, bx + 126, base_y - 40)
        glass.lineTo(bx + 126, shoulder + 70)
        glass.cubicTo(bx + 126, shoulder - 20, bx + 62, shoulder - 10, bx + 62, neck_top + 70)
        glass.lineTo(bx + 62, neck_top)
        glass.closeSubpath()
        g = QLinearGradient(bx - 126, 0, bx + 126, 0)
        g.setColorAt(0.0, QColor(206, 222, 244))
        g.setColorAt(0.28, QColor(255, 255, 255))
        g.setColorAt(0.75, QColor(250, 252, 255))
        g.setColorAt(1.0, QColor(200, 216, 240))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(glass)
        p.save()
        p.setClipPath(glass)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 236, 190, 150))                 # thin cream layer on top
        p.drawRect(QRectF(bx - 140, neck_top + 6, 280, 46))
        band = QPainterPath()
        band.addRoundedRect(QRectF(bx - 150, shoulder + 96, 300, 170), 24, 24)
        p.setBrush(BOWL_BAND)
        p.setPen(make_pen(DARK, 14))
        p.drawPath(band)
        p.restore()
        draw_heart(p, bx, shoulder + 180, 92, WHITE, 1.0)
        p.setPen(make_pen(QColor(255, 255, 255, 190), 18))      # glass shine
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(bx - 96, shoulder + 40), QPointF(bx - 96, shoulder + 70))
        p.drawLine(QPointF(bx - 96, shoulder + 285), QPointF(bx - 96, base_y - 70))
        p.setPen(make_pen(DARK, 22))
        p.drawPath(glass)
        p.setBrush(QColor(255, 108, 132))                       # cap
        cap = QRectF(bx - 76, neck_top - 54, 152, 66)
        p.drawRoundedRect(cap, 22, 22)
        p.setPen(make_pen(QColor(255, 255, 255, 200), 12))
        p.drawLine(QPointF(bx - 40, neck_top - 28), QPointF(bx + 40, neck_top - 28))

    def draw_bowl(self, p, t, top, phase, prog):
        cx, rim_y = self.mouth[0], self.mouth[1] + 235.0
        if phase == "arrive":
            off, drunk = 1000.0 * (1.0 - prog) ** 2, 0.0
        elif phase == "eat":
            off, drunk = 0.0, prog
        else:
            q = min(1.0, prog / 0.45)
            off, drunk = 1000.0 * q * q, 1.0
        if off >= 990.0:
            return
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        p.translate(0, off)
        edge = make_pen(DARK, 24)

        self.draw_milk_bottle(p, cx + 830.0, rim_y + 430.0)

        p.setPen(edge)
        p.setBrush(QColor(224, 204, 180))
        p.drawRoundedRect(QRectF(cx - 210, rim_y + 390, 420, 90), 40, 40)

        body = QPainterPath()
        body.moveTo(cx - 560, rim_y)
        body.cubicTo(cx - 540, rim_y + 330, cx - 330, rim_y + 445, cx, rim_y + 445)
        body.cubicTo(cx + 330, rim_y + 445, cx + 540, rim_y + 330, cx + 560, rim_y)
        body.closeSubpath()
        g = QLinearGradient(cx - 560, 0, cx + 560, 0)
        g.setColorAt(0.0, QColor(222, 200, 176))
        g.setColorAt(0.22, QColor(255, 250, 242))
        g.setColorAt(0.68, QColor(250, 240, 228))
        g.setColorAt(1.0, QColor(212, 188, 162))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(body)
        p.save()
        p.setClipPath(body)
        stripe = QPainterPath()
        stripe.moveTo(cx - 620, rim_y + 120)
        stripe.quadTo(cx, rim_y + 250, cx + 620, rim_y + 120)
        stripe.lineTo(cx + 620, rim_y + 205)
        stripe.quadTo(cx, rim_y + 335, cx - 620, rim_y + 205)
        stripe.closeSubpath()
        p.setPen(make_pen(DARK, 12))
        p.setBrush(BOWL_BAND)
        p.drawPath(stripe)
        draw_paw(p, cx, rim_y + 292, 62, WHITE)                 # white paw print on the blue stripe
        for k, hx in enumerate((-250, 250)):
            draw_heart(p, cx + hx, rim_y + 262 - 6 * (k % 2), 54, WHITE, 0.95)
        p.setPen(make_pen(QColor(255, 255, 255, 170), 22))      # shine on the left
        p.setBrush(Qt.BrushStyle.NoBrush)
        shine = QPainterPath()
        shine.moveTo(cx - 450, rim_y + 150)
        shine.quadTo(cx - 420, rim_y + 330, cx - 290, rim_y + 395)
        p.drawPath(shine)
        p.restore()
        p.setPen(edge)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(body)

        p.setPen(edge)
        p.setBrush(QColor(255, 251, 244))
        p.drawEllipse(QPointF(cx, rim_y), 560, 110)
        ig = QLinearGradient(0, rim_y - 84, 0, rim_y + 84)
        ig.setColorAt(0.0, QColor(196, 176, 152))
        ig.setColorAt(1.0, QColor(236, 222, 204))
        p.setPen(make_pen(QColor(190, 168, 144), 8))
        p.setBrush(QBrush(ig))
        p.drawEllipse(QPointF(cx, rim_y + 4), 505, 84)

        surf_y = rim_y + 14.0 + 34.0 * drunk
        mrx, mry = 482.0 * (1.0 - 0.26 * drunk), 72.0 * (1.0 - 0.5 * drunk)
        rg = QRadialGradient(QPointF(cx - 90, surf_y - 12), 520)
        rg.setColorAt(0.0, QColor(255, 255, 255))
        rg.setColorAt(0.7, QColor(250, 252, 255))
        rg.setColorAt(1.0, QColor(222, 234, 250))
        p.setPen(make_pen(MILK_EDGE, 10))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(cx, surf_y), mrx, mry)
        p.setPen(make_pen(QColor(255, 255, 255, 230), 12))      # glossy highlight on the milk
        p.setBrush(Qt.BrushStyle.NoBrush)
        gl = QPainterPath()
        gl.arcMoveTo(QRectF(cx - mrx * 0.8, surf_y - mry * 0.8, mrx * 1.6, mry * 1.6), 150)
        gl.arcTo(QRectF(cx - mrx * 0.8, surf_y - mry * 0.8, mrx * 1.6, mry * 1.6), 150, 55)
        p.drawPath(gl)
        p.setPen(Qt.PenStyle.NoPen)                             # tiny milk bubbles
        for bxo, byo, br in ((-250, 8, 22), (-205, -2, 13), (300, 12, 18), (260, 2, 10)):
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawEllipse(QPointF(cx + bxo * (1.0 - 0.2 * drunk), surf_y + byo * 0.6), br, br * 0.7)

        if phase == "eat" and drunk < 0.97:
            for k in range(2):                                  # ripples where the tongue laps
                rp = (t * 3.5 + k * 0.5) % 1.0
                ring = QColor(MILK_EDGE)
                ring.setAlphaF(1.0 - rp)
                p.setPen(QPen(ring, 9))
                p.setBrush(Qt.BrushStyle.NoBrush)
                r = 50.0 + 190.0 * rp
                p.drawEllipse(QPointF(cx, surf_y), r, r * 0.28)
            for k in range(5):                                  # splashing droplets
                dp = (t * 7.0 / math.pi + k / 5.0) % 1.0
                dx = cx + (k - 2) * 62.0 + 26.0 * math.sin(dp * 6.0 + k)
                dyy = surf_y - 8.0 - 190.0 * math.sin(math.pi * dp) * (0.55 + 0.1 * (k % 3))
                fade = min(1.0, (1.0 - dp) * 2.5)
                col = QColor(255, 255, 255, int(255 * fade))
                edge_c = QColor(MILK_EDGE)
                edge_c.setAlpha(int(255 * fade))
                p.setPen(QPen(edge_c, 8))
                p.setBrush(col)
                rr = 15.0 + 5.0 * (k % 2)
                p.drawEllipse(QPointF(dx, dyy), rr, rr * 1.2)

        x0, y0 = cx - 392.0, rim_y + 66.0
        drip = QPainterPath()
        drip.moveTo(x0 - 28, y0)
        drip.cubicTo(x0 - 28, y0 + 72, x0 - 38, y0 + 110, x0, y0 + 118)
        drip.cubicTo(x0 + 38, y0 + 110, x0 + 28, y0 + 72, x0 + 28, y0)
        drip.closeSubpath()
        p.setPen(make_pen(MILK_EDGE, 10))
        p.setBrush(MILK_COLOR)
        p.drawPath(drip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(QPointF(x0 - 9, y0 + 92), 6, 9)
        p.restore()

    def draw_feed_hearts(self, p, t, top, prog):
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        for k in range(5):
            hp = (t * 0.7 + k / 5.0) % 1.0
            x = 700.0 + k * 550.0 + 90.0 * math.sin(hp * 7.0 + k)
            y = 250.0 - 900.0 * hp
            fade = min(1.0, (1.0 - prog) * 3.0) * fade_loop(hp)
            draw_heart(p, x, y, 150.0 + 60.0 * (k % 2), HEART, fade)
        p.restore()

    def draw_walk_hearts(self, p, t, top):
        fade = min(1.0, max(0.0, (self.rise() - 0.55) / 0.4))
        if fade <= 0.0:
            return
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        for k in range(3):
            hp = (t * 0.45 + k / 3.0) % 1.0
            x = 1000.0 + k * 800.0 + 120.0 * math.sin(hp * 6.0 + k)
            y = 150.0 - 700.0 * hp
            draw_heart(p, x, y, 110.0 + 30.0 * (k % 2), HEART, 0.9 * fade * fade_loop(hp))
        p.restore()

    def tail_points(self, t):
        """Points along the tail. The bend travels along the tail, so it wags like a real one."""
        n = 26
        step = TAIL_LENGTH / n
        x, y = TAIL_BASE
        pts = [QPointF(x, y)]
        for i in range(1, n + 1):
            sp = i / n
            phi = 1.50 - 1.05 * sp + TAIL_WAG_SIZE * sp * math.sin(t * TAIL_WAG_SPEED - 2.4 * sp)
            x += math.sin(phi) * step
            y -= math.cos(phi) * step
            pts.append(QPointF(x, y))
        return pts

    def draw_tail(self, p, t, top):
        s = self.scale_
        pts = self.tail_points(t)
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.save()
        p.translate(0, top)
        p.scale(s, s)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for col, w in ((DARK, TAIL_FILL_W + 2.0 * TAIL_OUTLINE_W), (FUR, TAIL_FILL_W)):
            pen = QPen(col, w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)
        p.restore()

    def draw_butterflies(self, p, t, top, behind):
        fade = min(1.0, max(0.0, (self.rise() - 0.55) / 0.4))
        if fade <= 0.0:
            return
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        for k, (cx, cy, rx, ry, speed, start) in enumerate(BUTTERFLIES):
            a = start + t * speed + 0.35 * math.sin(t * 1.3 + k * 2.0)
            depth = math.sin(a)                     # > 0.45: flying behind the head
            if (depth > 0.45) != behind:
                continue
            wob = 1.0 + 0.07 * math.sin(t * 2.1 + k * 1.7)
            x = cx + rx * wob * math.cos(a)
            y = cy + ry * wob * math.sin(a) + 90.0 * math.sin(t * 5.0 + k)
            if behind:
                p.setOpacity(1.0)
            col1, col2 = BUTTERFLY_COLORS[k % len(BUTTERFLY_COLORS)]
            flap = t * (15.0 + 2.0 * k) + k
            tilt = 16.0 * math.cos(a) * (1 if speed > 0 else -1) + 8.0 * math.sin(t * 3.0 + k)
            draw_butterfly(p, x, y, BUTTERFLY_SIZE * (0.92 + 0.12 * k), col1, col2, flap, tilt, fade)
        p.restore()

    def draw_tears(self, p, t, top):
        s = self.scale_
        for i, (cx, cy) in enumerate(EYES):
            ox, oy = self.eye[i]
            ex = cx * s + ox * s
            ey = top + cy * s + oy * s + 60.0 * s
            for k in range(2):
                phase = ((t * 1.3) + k * 0.5) % 1.0
                drop_y = ey + (320.0 * s * phase)
                drop_x = ex + math.sin(phase * 3.0 + k) * 15.0 * s
                
                rx = 48.0 * s * (1.0 - phase * 0.2)
                ry = 72.0 * s * (1.0 - phase * 0.15)
                alpha = int(255 * min(1.0, (1.0 - phase) * 1.5))
                
                tear_color = QColor(TEAR)
                tear_color.setAlpha(alpha)
                border_color = QColor(TEAR_BORDER)
                border_color.setAlpha(alpha)
                
                p.save()
                p.setPen(QPen(border_color, max(2.0, 5.0 * s)))
                p.setBrush(tear_color)
                
                drop_path = QPainterPath()
                drop_path.moveTo(drop_x, drop_y - ry)
                drop_path.cubicTo(drop_x - rx, drop_y - ry * 0.3, drop_x - rx, drop_y + ry, drop_x, drop_y + ry)
                drop_path.cubicTo(drop_x + rx, drop_y + ry, drop_x + rx, drop_y - ry * 0.3, drop_x, drop_y - ry)
                p.drawPath(drop_path)

                shine_color = QColor(255, 255, 255, int(alpha * 0.8))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(shine_color)
                p.drawEllipse(QPointF(drop_x - rx * 0.3, drop_y + ry * 0.2), rx * 0.28, ry * 0.28)
                p.restore()

    def draw_mouth(self, p, emo, t, top):
        cx, cy, w, h = self.mouth
        s = self.scale_
        p.save()
        p.translate(cx * s, top + cy * s)
        p.scale(s, s)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FUR)
        p.drawRoundedRect(self.mouth_cover.translated(-cx, -cy), 40, 40)
        
        if emo == "playful":
            p.setBrush(CHEEK)
            for sx in (-1, 1):
                p.drawEllipse(QPointF(sx * 700, 40), 125, 72)
            bounce = 1.0 + 0.05 * math.sin(t * 7.0)
            smile = QPainterPath()
            smile.moveTo(-112, -52)
            smile.cubicTo(-96, 128 * bounce, 96, 128 * bounce, 112, -52)
            smile.quadTo(0, -22, -112, -52)
            stem = QPen(DARK, 24)
            stem.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(stem)
            p.drawLine(QPointF(0, -100), QPointF(0, -42))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(smile)
            p.save()
            p.setClipPath(smile)
            p.setBrush(TONGUE)
            p.drawEllipse(QPointF(0, 92 * bounce), 62, 40)
            p.restore()
            pen = QPen(DARK, 24)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(smile)
        elif emo == "blush":
            w_mouth = QPainterPath()
            w_mouth.moveTo(-60, -25)
            w_mouth.cubicTo(-40, 15, -10, 15, 0, -10)
            w_mouth.cubicTo(10, 15, 40, 15, 60, -25)
            pen = QPen(DARK, 22)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(w_mouth)
        elif emo == "whistle":
            beat = math.sin(t * 9.0)
            puff = 1.0 + 0.06 * beat
            p.setBrush(CHEEK)
            for sx in (-1, 1):
                p.drawEllipse(QPointF(sx * 520, 25), 120 * puff, 85 * puff)
            rx, ry = 58.0 * (1.0 + 0.06 * beat), 66.0 * (1.0 + 0.06 * beat)
            line = QPen(DARK, 26)
            line.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(line)
            p.drawLine(QPointF(0, -100), QPointF(0, 28 - ry))
            p.setBrush(QColor(255, 175, 185))
            p.drawEllipse(QPointF(0, 28), rx, ry)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawEllipse(QPointF(-rx * 0.38, 28 - ry * 0.38), rx * 0.18, ry * 0.12)
            for k in range(2):
                prog = (t * 1.5 + k * 0.5) % 1.0
                x = rx + 90 + 150 * prog
                wave = QPainterPath()
                wave.arcMoveTo(QRectF(x - 60, -95, 120, 190), -45)
                wave.arcTo(QRectF(x - 60, -95, 120, 190), -45, 90)
                wpen = QPen(QColor(90, 125, 215), 22)
                wpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setOpacity(fade_loop(prog))
                p.setPen(wpen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(wave)
            p.setOpacity(1.0)
        elif emo == "eat":
            chew = abs(math.sin(t * 8.5))
            puff = 1.0 + 0.10 * chew
            p.setBrush(CHEEK)
            for sx in (-1, 1):
                p.drawEllipse(QPointF(sx * 560, 30), 130 * puff, 90 * puff)
            mw, mh = 70.0 + 30.0 * chew, 26.0 + 110.0 * chew
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(0, mh / 2 - 40), mw, mh / 2)
            stem = QPen(DARK, 24)
            stem.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(stem)
            p.drawLine(QPointF(0, -100), QPointF(0, -40))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(mouth)
            pen = QPen(DARK, 24)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mouth)
        elif emo == "drink":
            lap = abs(math.sin(t * 7.0))
            L = 150.0 + 135.0 * lap
            sway = 4.0 * math.sin(t * 3.5)
            stem = make_pen(DARK, 24)
            p.setPen(stem)
            p.drawLine(QPointF(0, -100), QPointF(0, -45))
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(0, 22), 135, 62)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(mouth)
            p.setPen(make_pen(DARK, 24))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mouth)

            p.save()
            p.rotate(sway)
            tongue = QPainterPath()
            tongue.moveTo(-72, 4)
            tongue.cubicTo(-82, L * 0.30, -134, L * 0.46, -124, L * 0.78)
            tongue.cubicTo(-116, L * 1.10, 116, L * 1.10, 124, L * 0.78)
            tongue.cubicTo(134, L * 0.46, 82, L * 0.30, 72, 4)
            tongue.closeSubpath()
            tg = QLinearGradient(0, 0, 0, L)
            tg.setColorAt(0.0, QColor(240, 108, 132))
            tg.setColorAt(0.65, QColor(255, 140, 160))
            tg.setColorAt(1.0, QColor(255, 176, 190))
            p.setPen(make_pen(QColor(200, 70, 96), 14))
            p.setBrush(QBrush(tg))
            p.drawPath(tongue)
            p.save()
            p.setClipPath(tongue)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(make_pen(QColor(214, 78, 104), 10))          # centre groove
            groove = QPainterPath()
            groove.moveTo(0, 26)
            groove.quadTo(12, L * 0.45, 0, L * 0.80)
            p.drawPath(groove)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 205, 214, 200))                # little bumps on the tongue
            for dxp, fy in ((-62, 0.42), (62, 0.42), (-86, 0.62), (86, 0.62),
                            (-38, 0.60), (38, 0.60), (-52, 0.78), (52, 0.78)):
                p.drawEllipse(QPointF(dxp, L * fy), 9, 9)
            p.setBrush(QColor(255, 255, 255, 110))                # wet shine at the tip
            p.drawEllipse(QPointF(-55, L * 0.88), 30, 11)
            p.restore()
            p.restore()
        elif emo == "yawn":
            k = yawn_amount(self.mood_phase(t, YAWN_SECONDS))
            if k > 0.9:
                k += 0.025 * math.sin(t * 17.0)                  # the wide yawn trembles a little
            mw, mh = 70.0 + 125.0 * k, 24.0 + 410.0 * k
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(0, mh / 2 - 45), mw, mh / 2)
            p.setPen(make_pen(DARK, 24))
            p.drawLine(QPointF(0, -100), QPointF(0, -45))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(mouth)
            p.save()
            p.setClipPath(mouth)
            p.setBrush(TONGUE)
            p.drawEllipse(QPointF(0, mh * 0.88 - 45), mw * 0.78, mh * 0.34)
            if k > 0.3:                                          # two tiny fangs
                p.setBrush(WHITE)
                for fx in (-0.42, 0.42):
                    fang = QPainterPath()
                    fang.moveTo(fx * mw - 24, -50)
                    fang.lineTo(fx * mw + 24, -50)
                    fang.lineTo(fx * mw, -50 + 70.0 * k)
                    fang.closeSubpath()
                    p.drawPath(fang)
            p.restore()
            p.setPen(make_pen(DARK, 24))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mouth)
        elif emo == "sneeze":
            ph = self.mood_phase(t, SNEEZE_SECONDS)
            build, burst = sneeze_build(ph), sneeze_burst(ph)
            if burst < 0.04 and build < 0.04:
                p.setPen(make_pen(DARK, 22))
                p.drawLine(QPointF(0, -100), QPointF(0, -40))
                w_mouth = QPainterPath()
                w_mouth.moveTo(-60, -25)
                w_mouth.cubicTo(-40, 15, -10, 15, 0, -10)
                w_mouth.cubicTo(10, 15, 40, 15, 60, -25)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(w_mouth)
            else:
                if burst >= 0.04:
                    mw, mh = 120.0 + 70.0 * burst, 130.0 + 150.0 * burst
                else:
                    pulse = 0.5 + 0.5 * math.sin(t * 13.0)            # "ah... ah..."
                    mw, mh = 55.0 + 50.0 * build, 22.0 + (90.0 + 60.0 * pulse) * build
                mouth = QPainterPath()
                mouth.addEllipse(QPointF(0, mh / 2 - 45), mw, mh / 2)
                p.setPen(make_pen(DARK, 24))
                p.drawLine(QPointF(0, -100), QPointF(0, -45))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(90, 30, 40))
                p.drawPath(mouth)
                p.save()
                p.setClipPath(mouth)
                p.setBrush(TONGUE)
                p.drawEllipse(QPointF(0, mh * 0.86 - 45), mw * 0.74, mh * 0.32)
                p.restore()
                p.setPen(make_pen(DARK, 24))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(mouth)
            if 0.58 < ph < 0.95:                                  # the spray
                dp = min(1.0, (ph - 0.58) / 0.30)
                for k in range(11):
                    a = math.pi / 2.0 + (k - 5) * 0.27
                    reach = 0.65 + 0.35 * (((k * 37) % 10) / 9.0)
                    dist = 140.0 + 780.0 * reach * (1.0 - (1.0 - dp) ** 2)
                    x = math.cos(a) * dist * 1.15
                    y = 60.0 + math.sin(a) * dist * 0.85 + 90.0 * dp * dp
                    r = (30.0 - 14.0 * dp) * (0.8 + 0.4 * ((k * 53) % 7) / 6.0)
                    col = QColor(SPRAY)
                    col.setAlphaF(max(0.0, 1.0 - dp * dp))
                    edge_c = QColor(TEAR_BORDER)
                    edge_c.setAlphaF(max(0.0, 1.0 - dp * dp))
                    p.setPen(QPen(edge_c, 6))
                    p.setBrush(col)
                    p.drawEllipse(QPointF(x, y), r, r * 1.25)
        elif emo == "talk":
            opened = 0.15 + 0.85 * abs(math.sin(t * 10.5))
            mw, mh = 62.0 + 26.0 * opened, 22.0 + 120.0 * opened
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(0, mh / 2 - 40), mw, mh / 2)
            stem = QPen(DARK, 24)
            stem.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(stem)
            p.drawLine(QPointF(0, -100), QPointF(0, -40))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(mouth)
            p.save()
            p.setClipPath(mouth)
            p.setBrush(TONGUE)
            p.drawEllipse(QPointF(0, mh * 0.85 - 40), mw * 0.75, mh * 0.34)
            p.restore()
            pen = QPen(DARK, 24)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mouth)
        else:
            # singing: the mouth opens and closes like syllables (not like a steady yawn), and the
            # vowel slowly changes between a narrow "ooh" and a wide "aah"
            syllable = abs(math.sin(t * 5.3)) * (0.65 + 0.35 * math.sin(t * 1.9 + 1.0))
            opened = 0.25 + 0.75 * min(1.0, syllable)
            vowel = 0.5 + 0.5 * math.sin(t * 1.3)
            mw, mh = 115.0 + 55.0 * vowel, 60.0 + 215.0 * opened
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(0, mh / 2 - 55), mw, mh / 2)
            stem = QPen(DARK, 26)
            stem.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(stem)
            p.drawLine(QPointF(0, -100), QPointF(0, -55))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 30, 40))
            p.drawPath(mouth)
            p.save()
            p.setClipPath(mouth)
            p.setBrush(TONGUE)
            p.drawEllipse(QPointF(0, mh * 0.85 - 55), mw * 0.75, mh * 0.34)
            p.restore()
            pen = QPen(DARK, 26)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mouth)
        p.restore()

    def body_motion(self, p, emo, t, top):
        """Move the painter the way the body moves (sway, bounce, stretch...)."""
        tr = self.body_xform(emo, t, top)
        if tr is not None:
            p.setWorldTransform(tr, True)

    def dance_step(self, t):
        """(lean, beat) of the dance at time t. lean goes -1..1: +1 = the body leans over the LEFT paw
        (so the right paw is free), -1 = over the right paw. beat is +1 when the body passes the middle
        (up, stretched) and -1 at both ends (down, squashed): two bounces for every sway."""
        th = DANCE_SPEED * t
        return math.sin(th), math.cos(2.0 * th)

    def body_xform(self, emo, t, top):
        """The way the body is moved right now, as a QTransform (None = it stands still).
        body_motion() applies it to the picture, and draw_paws() uses the very same transform to
        move the paws, so the paws always stay attached to the body."""
        w, h = float(self.cat_w), float(self.cat_h)
        hop = 0.0
        gait = self.features.gait() if self.features is not None else None
        if emo == "dance":
            # The cat dances like a person: the feet stay on the ground and the body pivots over them.
            # So the pivot is the taskbar edge (where the paws are), in the middle of the body, and not
            # the hidden bottom of the picture (that made the body slide over paws that did not move).
            lean, beat = self.dance_step(t)
            edge = self.pad + self.cat_h
            mid = getattr(self, "paw_mid_px", w / 2.0)
            tr = QTransform()
            tr.translate(0.0, -DANCE_BOUNCE * h * beat)
            tr.translate(mid, edge)
            tr.shear(DANCE_LEAN * lean, 0.0)
            tr.scale(1.0 - DANCE_SQUASH * beat, 1.0 + DANCE_SQUASH * beat)
            tr.translate(-mid, -edge)
            return tr
        elif emo == "singing":
            sh = 0.03 * w / h * math.sin(t * 3.0)
            sx, sy = 0.94, 1.0
            hop = 0.010 * h * abs(math.sin(t * 5.3))     # a little bob on every syllable (same beat as the mouth)
        elif emo == "playful":
            sh = 0.022 * w / h * math.sin(t * 3.4)
            sx, sy = 0.985, 1.0 + 0.014 * math.sin(t * 6.8)
        elif emo == "confused":
            sh = 0.03 * w / h * (0.7 + 0.3 * math.sin(t * 2.4))
            sx, sy = 0.94, 1.0
        elif emo in ("cry", "emotional", "blush"):
            sh = 0.025 * w / h * math.sin(t * 2.5)
            sx, sy = 0.97, 1.0 + 0.015 * math.sin(t * 3.5)
        elif emo in ("eat", "drink"):
            sh, sx = 0.0, 1.0
            sy = 1.0 + 0.012 * math.sin(t * (9.0 if emo == "eat" else 7.0))
        elif emo == "sleeping":
            curl = self.features.curl_amount(t) if self.features is not None else 0.0
            sh = -0.05 * w / h * curl                # leans over, then curls up (good night routine)
            sx = 1.0 + 0.05 * curl
            sy = 1.0 + 0.012 * math.sin(t * 1.8) - 0.09 * curl
        elif emo == "yawn":
            k = yawn_amount(self.mood_phase(t, YAWN_SECONDS))      # a nice big stretch
            sh, sx, sy = 0.0, 1.0 - 0.03 * k, 1.0 + 0.045 * k
        elif emo == "sneeze":
            ph = self.mood_phase(t, SNEEZE_SECONDS)
            build, burst = sneeze_build(ph), sneeze_burst(ph)
            sh = 0.012 * w / h * math.sin(t * 38.0) * build        # trembling before the sneeze
            sx = 1.0 - 0.02 * build + 0.07 * burst                 # then a jolt forward
            sy = 1.0 + 0.035 * build - 0.08 * burst
        elif gait is not None:
            speed, step = gait["speed"], gait["phase"]
            if gait["mode"] == "walk":
                lift = abs(math.sin(step))
                sh = (0.03 * gait["dir"] * speed + 0.02 * math.sin(step) * speed) * w / h
                sx = 1.0 + 0.012 * speed * math.cos(2.0 * step)
                sy = 1.0 + 0.035 * speed * (lift - 0.5)
                hop = 0.022 * h * speed * lift
            else:
                breathe = math.sin(t * 2.2)
                sh, sx, sy = 0.0, 1.0 + 0.006 * breathe, 0.975 + 0.012 * breathe
        else:
            return None
        bottom = top + h
        tr = QTransform()
        tr.translate(0.0, -hop)
        tr.translate(w / 2.0, bottom)
        tr.shear(sh, 0.0)
        tr.scale(sx, sy)
        tr.translate(-w / 2.0, -bottom)
        return tr

    def draw_symbols(self, p, emo, t, top):
        if emo not in SYMBOL_MOODS:
            return
        base = min(1.0, max(0.0, (self.rise() - 0.55) / 0.4))
        if base <= 0.0:
            return
        p.save()
        p.translate(0, top)
        p.scale(self.scale_, self.scale_)
        if emo == "sleeping":
            for k in range(3):
                prog = (t * 0.32 + k / 3.0) % 1.0
                x = 2650 + 260 * prog + 70 * math.sin(prog * 9.0 + k)
                y = 330 - 820 * prog
                draw_z(p, x, y, 130 + 190 * prog, ZZZ_COLOR, base * fade_loop(prog),
                       12 - 24 * prog)
            if self.features is not None:
                self.features.draw_night(p, t, base)
        elif emo == "confused":
            sw = math.sin(t * 3.2)
            draw_question(p, 2300 + 70 * math.sin(t * 2.0), -320 + 30 * math.sin(t * 4.0),
                          235 * (1.0 + 0.06 * sw), QUESTION_COLOR, base, 14 * sw)
            draw_question(p, 1050 + 40 * math.sin(t * 2.6), -170 + 25 * math.sin(t * 3.5),
                          170 * (1.0 - 0.06 * sw), QUESTION_COLOR, base, -14 * sw)
        elif emo == "sneeze":
            ph = self.mood_phase(t, SNEEZE_SECONDS)
            burst = sneeze_burst(ph)
            if burst > 0.02:
                grow = 0.55 + 0.45 * smooth((ph - 0.58) / 0.06) + 0.08 * math.sin(t * 20.0)
                draw_word(p, "ACHOO!", 1805, -250, 300, SNEEZE_COLOR, base * min(1.0, burst * 1.5),
                          -7.0, grow)
        elif emo == "yawn":
            ph = self.mood_phase(t, YAWN_SECONDS)
            a = smooth((ph - 0.22) / 0.15) * (1.0 - smooth((ph - 0.70) / 0.20))
            if a > 0.02:
                draw_word(p, "Yaaawn~", 2500, -170 - 90.0 * ph, 230, YAWN_COLOR, base * a, 8.0)
        elif emo == "singing":
            self.note_stream(p, t, base, [700, 1500, 2300, 3050], 0.30, 190, 820, 120, True)
        elif emo == "whistle":
            self.note_stream(p, t, base, [2700, 3050], 0.26, 150, 820, 90, False)
        elif emo == "dance":
            self.note_stream(p, t, base, [500, 1250, 2000, 2750, 3300], 0.45, 160, 820, 160, True)
        p.restore()

    def note_stream(self, p, t, base, xs, speed, size, rise, sway, mixed):
        n = len(xs)
        for k, x0 in enumerate(xs):
            prog = (t * speed + k / n) % 1.0
            x = x0 + sway * math.sin(prog * 8.0 + k * 1.9)
            y = 380 - rise * prog
            angle = 18 * math.sin(prog * 7.0 + k)
            draw_music_note(p, x, y, size, NOTE_COLORS[k % len(NOTE_COLORS)],
                            base * fade_loop(prog), mixed and k % 2 == 1, angle)

    def draw_eye(self, p, emo, i, ox, oy):
        inner = 1 if i == 0 else -1
        t = time.perf_counter()
        p.setPen(Qt.PenStyle.NoPen)

        if emo == "whistle":
            ox = EYE_MAX_X * 0.85 * math.sin(t * 1.4)
            oy = -EYE_MAX_Y * 0.8
        elif emo == "confused":
            ox = EYE_MAX_X * 0.8 * math.sin(t * 3.0 + i * 0.8)
            oy = EYE_MAX_Y * 0.3 * math.sin(t * 2.2)
        elif emo == "blush":
            ox = ox * 0.3
            oy = oy * 0.3 + 28.0

        if emo == "sleeping":
            pen = QPen(DARK, 36)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(-92, -8)
            path.quadTo(0, 96, 92, -8)
            p.drawPath(path)
            return

        if emo == "singing":
            pen = QPen(DARK, 34 + 6 * math.sin(t * 6.0))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(-inner * 85, -75)
            path.lineTo(inner * 75, 0)
            path.lineTo(-inner * 85, 75)
            p.drawPath(path)
            return

        if emo == "yawn":
            k = yawn_amount(self.mood_phase(t, YAWN_SECONDS))
            if k > 0.5:                                           # eyes squeezed shut
                pen = QPen(DARK, 40)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath()
                path.moveTo(-92, 0)
                path.quadTo(0, 100, 92, 0)
                p.drawPath(path)
                tk = min(1.0, (k - 0.5) * 2.0)                    # a tiny yawn tear
                if tk > 0.05:
                    tx, ty = -inner * 112.0, 40.0 + 80.0 * tk
                    rx, ry = 26.0 * tk + 2.0, 42.0 * tk + 2.0
                    drop = QPainterPath()
                    drop.moveTo(tx, ty - ry)
                    drop.cubicTo(tx - rx, ty - ry * 0.3, tx - rx, ty + ry, tx, ty + ry)
                    drop.cubicTo(tx + rx, ty + ry, tx + rx, ty - ry * 0.3, tx, ty - ry)
                    p.setPen(QPen(TEAR_BORDER, 8))
                    p.setBrush(TEAR)
                    p.drawPath(drop)
                    p.setPen(Qt.PenStyle.NoPen)
                return
        elif emo == "sneeze":
            ph = self.mood_phase(t, SNEEZE_SECONDS)
            if sneeze_burst(ph) > 0.25:                           # scrunched  > <  eyes
                pen = QPen(DARK, 42)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath()
                path.moveTo(-inner * 85, -75)
                path.lineTo(inner * 75, 0)
                path.lineTo(-inner * 85, 75)
                p.drawPath(path)
                return

        if emo in ("happy", "playful", "eat", "drink"):
            pen = QPen(DARK, 42)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(-92, 38)
            path.quadTo(0, -92, 92, 38)
            p.drawPath(path)
            return

        if emo == "love":
            beat = 1.0 + 0.08 * math.sin(t * 8.0)
            p.save()
            p.translate(ox * 0.25, oy * 0.25 + 6)
            p.scale(beat, beat)
            path = QPainterPath()
            path.moveTo(0, 92)
            path.cubicTo(-160, -18, -88, -118, 0, -38)
            path.cubicTo(88, -118, 160, -18, 0, 92)
            p.setBrush(HEART)
            p.drawPath(path)
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawEllipse(QPointF(-52, -40), 20, 14)
            p.restore()
            return

        if emo == "surprised":
            grow = 1.15
        elif emo in ("dance", "emotional"):
            grow = 1.10
        elif emo == "blush":
            grow = 0.98
        elif emo == "confused":
            grow = 1.12 if i == 0 else 0.86
        else:
            grow = 1.0
        sy = (1.0 if emo in ("surprised", "sleepy", "emotional", "cry", "blush", "yawn", "sneeze")
              else 1.0 - 0.92 * self.closure)

        p.save()
        p.translate(ox, oy)
        p.scale(grow, grow * sy)
        p.setBrush(DARK)
        p.drawEllipse(QPointF(0, 0), EYE_RX, EYE_RY)
        p.setBrush(WHITE)

        if emo == "emotional":
            p.drawEllipse(QPointF(-28, -48), 38, 38)
            p.drawEllipse(QPointF(32, 32), 22, 22)
            p.drawEllipse(QPointF(-36, 36), 14, 14)
        else:
            p.drawEllipse(QPointF(-32, -48), 31, 31)
            p.drawEllipse(QPointF(34, 38), 14, 14)

        if emo in ("sad", "cry"):
            p.drawEllipse(QPointF(8, 72), 24, 14)
        elif emo == "dance":
            p.drawEllipse(QPointF(52, -14), 13, 13)
        p.restore()

        if emo in ("emotional", "blush"):
            color = BLUSH_CHEEK if emo == "blush" else CHEEK
            p.setBrush(color)
            p.drawEllipse(QPointF(-inner * 60, 110), 125, 62)
            
            if emo == "blush":
                pen = QPen(BLUSH_HATCH, 18)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                cx_base = -inner * 60
                for h in range(-2, 3):
                    hx = cx_base + h * 24
                    p.drawLine(QPointF(hx - 15, 85), QPointF(hx + 15, 135))
                p.setPen(Qt.PenStyle.NoPen)

        if emo == "sleepy":
            lid0 = 0.42 + 0.08 * math.sin(t * 1.3)
            lid = lid0 + (1.0 - lid0) * 0.97 * self.closure
            self.draw_lid(p, -EYE_RY + 2.0 * EYE_RY * lid)
        elif emo == "yawn":
            k = yawn_amount(self.mood_phase(t, YAWN_SECONDS))
            lid = 0.8 * min(1.0, k / 0.5)                         # eyelids sink as the yawn starts
            if lid > 0.03:
                self.draw_lid(p, -EYE_RY + 2.0 * EYE_RY * lid)
        elif emo == "sneeze":
            lid = 0.38 * sneeze_build(self.mood_phase(t, SNEEZE_SECONDS))   # eyes squint, watering
            if lid > 0.03:
                self.draw_lid(p, -EYE_RY + 2.0 * EYE_RY * lid)
        elif emo == "blush":
            lid = 0.32 + 0.05 * math.sin(t * 1.8)
            self.draw_lid(p, -EYE_RY + 2.0 * EYE_RY * lid)
            self.draw_brow(p, inner, -30.0, -90.0)
        elif emo == "angry":
            self.draw_brow(p, inner, -120.0, 28.0)
        elif emo == "confused" and i == 1:
            self.draw_brow(p, inner, -45.0, -45.0)
        elif emo in ("sad", "cry"):
            self.draw_brow(p, inner, -42.0, -150.0)

    def draw_lid(self, p, y):
        p.save()
        p.setClipRect(QRectF(-205, -191, 410, y + 191))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FUR)
        p.drawRoundedRect(REL_COVER, 60, 60)
        p.restore()
        if y < EYE_RY:
            half = EYE_RX * math.sqrt(max(0.0, 1.0 - (y / EYE_RY) ** 2))
            pen = QPen(DARK, 20)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(-half, y), QPointF(half, y))
            p.setPen(Qt.PenStyle.NoPen)

    def draw_brow(self, p, inner, y_outer, y_inner):
        xo, xi = -inner * 210.0, inner * 210.0
        path = QPainterPath()
        path.moveTo(xo, -191)
        path.lineTo(xi, -191)
        path.lineTo(xi, y_inner)
        path.lineTo(xo, y_outer)
        path.closeSubpath()
        p.save()
        p.setClipPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FUR)
        p.drawRoundedRect(REL_COVER, 60, 60)
        p.restore()

        def edge(x):
            return y_outer + (x - xo) * (y_inner - y_outer) / (xi - xo)
        x1, x2 = -inner * EYE_RX * 0.98, inner * EYE_RX * 0.98
        pen = QPen(DARK, 22)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, edge(x1)), QPointF(x2, edge(x2)))
        p.setPen(Qt.PenStyle.NoPen)


TRAY_MENU_STYLE = """
QMenu { background: #fffaf3; border: 1px solid #ecc6a6; border-radius: 10px; padding: 6px;
        font-family: @FONT@; font-size: 13px; color: #2b2622; }
QMenu::item { padding: 8px 32px 8px 14px; margin: 1px 2px; border-radius: 8px; background: transparent; }
QMenu::item:selected { background: #ffe2cc; color: #2b2622; }
QMenu::item:pressed { background: #ffd2b3; }
QMenu::item:disabled { color: #b0a79c; }
QMenu::separator { height: 1px; background: #ead3bd; margin: 5px 10px; }
QMenu::indicator { width: 14px; height: 14px; margin-left: 8px; border: 1px solid #ecc6a6;
                   border-radius: 4px; background: #ffffff; }
QMenu::indicator:checked { background: #ff8f5c; border: 1px solid #f0763d; }
QLabel { color: #2b2622; background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #ead3bd; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #ff8f5c; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffffff; border: 2px solid #ff8f5c; width: 12px; height: 12px;
                             margin: -6px 0; border-radius: 8px; }
""".replace("@FONT@", FONT_STACK)


def main():
    install_error_log()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Peeking Cat")

    lock = QLockFile(os.path.join(tempfile.gettempdir(), "peeking_cat.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Peeking Cat",
                                "Peeking Cat is already running.\nLook for the cat icon near the clock "
                                "(it may be inside the ^ arrow).")
        sys.exit(0)

    for _ in range(60):
        if QSystemTrayIcon.isSystemTrayAvailable():
            break
        time.sleep(1)

    cat = PeekingCat(app)
    app.aboutToQuit.connect(cat.prepare_quit)
    # Windows shutdown / sign-out: save first, and keep the open sticky notes marked "open"
    app.commitDataRequest.connect(cat.prepare_quit, Qt.ConnectionType.DirectConnection)
    if cat.features is not None:
        app.aboutToQuit.connect(cat.features.shutdown)
    for name, err in _MODULE_ERRORS.items():
        log_error("%s could not be imported: %s" % (name, err))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()