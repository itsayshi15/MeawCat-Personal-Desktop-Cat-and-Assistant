"""
youtube_music.py - YouTube music (sound only) for Peeking Cat
==============================================================
* Tray > "YouTube music" > "Search and play..." opens a small window.
* Type a song or an artist (or paste a YouTube link) and press Enter. The results appear in a list.
  Double-click a result: only the SOUND is played. No video is shown anywhere.
* Buttons: previous, pause / play, stop, next, a seek bar and a volume slider.
  When a song ends, the next result starts by itself (you can switch that off).
* The cat reacts:
    - while a song plays, the cat stays up and shows a message with the song name and the time
      ("Now playing"). Switch it off: tray > YouTube music > "Cat shows the song name"
    - while a song plays, the cat sings along (music notes, singing mouth). It does not dance.
      Switch it off: tray > YouTube music > "Cat sings along"
    - when YouTube is open in front of you in a browser, it says hello (with the name of the video),
      and after a long time it reminds you to rest your eyes
      (tray > YouTube music > "Cat reacts to YouTube").
      It only reads the TITLE of the window in front. Nothing is stored or sent anywhere.
* A song starts as soon as YouTube has given the link (a few seconds): the sound is streamed, so
  you do not wait for a download. If streaming does not work for a song, the program downloads
  the sound-only file into the folder "youtube_cache" next to this file instead (the newest 20 are
  kept) and plays it from there. A song that was downloaded before starts at once.

What you need (once):
    pip install -U "yt-dlp[default]"
  and a JavaScript runtime that YouTube's downloader needs: Deno (winget install DenoLand.Deno)
  or Node.js (nodejs.org). If one of them is in the PATH, the program finds it by itself.
  Keep yt-dlp updated (the same pip command): YouTube changes often.

The rest (sound playback) is already inside PySide6 (QtMultimedia), nothing else to install.
If this file or yt-dlp is missing, the cat still starts (the menu item just does not appear).
"""
import glob
import os
import random
import re
import shutil
import sys
import threading
import time

# A .pyw program has no console: stdout and stderr are None, and yt-dlp writes to them.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSlider, QVBoxLayout)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MM_ERROR = ""
except Exception as _err:                    # QtMultimedia missing in this PySide6
    QAudioOutput = QMediaPlayer = None
    _MM_ERROR = str(_err)

try:
    import yt_dlp
    _YT_ERROR = ""
except Exception as _err:                    # yt-dlp not installed for this Python
    yt_dlp = None
    _YT_ERROR = str(_err)

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

# ----------------------------------------------------------------------
# SETTINGS you can change
# ----------------------------------------------------------------------
CACHE_DIR = "youtube_cache"      # sound files are kept here (next to this file)
CACHE_KEEP = 20                  # how many of the newest songs to keep
SEARCH_RESULTS = 12              # how many results to show
MAX_MINUTES = 180                # longer videos are not downloaded (3 hours)
DEFAULT_VOLUME = 60              # 0 to 100
SOCKET_TIMEOUT = 20              # seconds to wait for YouTube
STREAM_WAIT_SECONDS = 20         # a streamed song that has not started after this long is downloaded instead
WATCH_POLL_MS = 1000             # how often the cat looks at the title of the window in front
WATCH_CONFIRM_SECONDS = 2.0      # you must stay on YouTube this long before the cat says hello
HELLO_COOLDOWN = 3 * 60          # the hello at most once in 3 minutes
WATCH_RESET_SECONDS = 5 * 60     # away from YouTube this long = a new watching session
REST_EYES_MINUTES = 45           # remind to rest the eyes after this long on YouTube
REST_COOLDOWN = 40 * 60          # and then at most once in 40 minutes
TEST_SECONDS = 6                 # "Test: what does the cat see?" waits this long, so you can switch windows

_YT_TITLE = re.compile(r"\byoutube\b", re.I)
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TEMP_NAME = re.compile(r"^[A-Za-z0-9_-]{11}\.f[0-9a-z-]+\.\w+$")      # e.g. abc123DEF45.f140.m4a

HELLO_LINES = [("YouTube time! Enjoy!", "happy"),
               ("Ooh, a video! I will sit quietly.", None),
               ("Music or videos? Both are fun!", "singing"),
               ("Remember to drink some water!", "happy"),
               ("Turn the sound up. I like music!", "happy")]
REST_TEXT = "You have been on YouTube for a while. Look far away for 20 seconds. Rest your eyes!"

EXTRA_STYLE = """
QSlider::groove:horizontal { height: 6px; background: #f3e3d3; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #ff8f5c; border-radius: 3px; }
QSlider::handle:horizontal { background: #ff8f5c; border: 1px solid #f0763d; width: 14px;
                             margin: -5px 0; border-radius: 7px; }
QCheckBox { color: #2b2622; font-size: 13px; }
"""


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def fmt_time(seconds):
    try:
        s = max(0, int(seconds))
    except (TypeError, ValueError):
        return "?:??"
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, sec) if h else "%d:%02d" % (m, sec)


def short(text, limit=40):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def is_temp_file(path):
    """True for half-finished download pieces (not a finished song)."""
    name = os.path.basename(path)
    return name.endswith((".part", ".ytdl", ".temp")) or bool(_TEMP_NAME.match(name))


def video_id_from(text):
    """The 11-letter video id of a pasted YouTube link, or None."""
    m = _VIDEO_ID.search(text)
    return m.group(1) if m else None


def video_name(title):
    """The name of the video in a browser window title, or "" if there is none.
    "(3) Lofi beats - YouTube - Google Chrome" -> "Lofi beats"."""
    name = re.split(r"\s+[-–—|]\s+YouTube\b", str(title), maxsplit=1, flags=re.I)[0]
    name = re.sub(r"^\(\d+\)\s*", "", name).strip()          # "(3)" in front = unread notifications
    if not name or re.match(r"youtube\b", name, re.I):       # the front page: no video name
        return ""
    return name


def js_runtimes():
    """The JavaScript runtimes (Deno, Node, Bun) that are installed. YouTube's downloader needs one.
    Returns {name: {}} for yt-dlp (empty dict = none found)."""
    return {name: {} for name in ("deno", "node", "bun") if shutil.which(name)}


def clean_error(err):
    """Turn a yt-dlp error into one short sentence a person can act on."""
    text = _ANSI.sub("", str(err)).strip()
    text = re.sub(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*)?(?:[\w-]{11}:\s*)?", "", text)
    low = text.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return "YouTube wants a sign-in for this video. Try another one."
    if "requested format" in low:
        return ("YouTube did not give me a sound file. Update yt-dlp:  pip install -U \"yt-dlp[default]\"  "
                "and install Deno or Node.js.")
    if "private video" in low or "video unavailable" in low or "not available" in low:
        return "This video is not available. Try another one."
    if "age" in low and "restrict" in low:
        return "This video is age-restricted. Try another one."
    if "403" in low or "javascript" in low or "n challenge" in low or "po token" in low:
        return ("YouTube refused the download. Update yt-dlp:  pip install -U \"yt-dlp[default]\"  "
                "and install Deno or Node.js.")
    if any(w in low for w in ("getaddrinfo", "timed out", "timeout", "unable to download webpage",
                              "connection", "network is unreachable")):
        return "I could not reach YouTube. Are you online?"
    return short(text or "Something went wrong.", 200)


_user32 = None


def foreground_title():
    """(title of the window in front, id of its program). ("", 0) if unknown."""
    global _user32
    if sys.platform != "win32":
        return "", 0
    try:
        if _user32 is None:                      # our own copy of user32, so other modules' settings are not touched
            _user32 = ctypes.WinDLL("user32")
            _user32.GetForegroundWindow.restype = wintypes.HWND
            _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32 = _user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", 0
        n = min(512, max(0, user32.GetWindowTextLengthW(hwnd)))
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return buf.value, int(pid.value)
    except Exception:
        return "", 0


class _Quiet:
    """yt-dlp logger that prints nothing and remembers the last problem."""

    def __init__(self):
        self.last_error = ""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.last_error = str(msg)


def ydl_options(logger, **extra):
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "logger": logger,
            "noplaylist": True, "socket_timeout": SOCKET_TIMEOUT, "retries": 3}
    runtimes = js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    opts.update(extra)
    return opts


# ----------------------------------------------------------------------
# the window
# ----------------------------------------------------------------------
class YouTubeWindow(QDialog):
    def __init__(self, svc, style):
        super().__init__()
        self.s = svc
        self.setWindowTitle("Cat assistant - YouTube music")
        self.setMinimumSize(600, 660)
        self.setStyleSheet(style + EXTRA_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)

        title = QLabel("YouTube music")
        title.setObjectName("h1")
        root.addWidget(title)
        hint = QLabel("Type a song or an artist, or paste a YouTube link. Only the sound is played. "
                      "No video is shown.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.tip = QLabel()
        self.tip.setObjectName("hint")
        self.tip.setWordWrap(True)
        self.tip.setStyleSheet("color: #c0392b;")
        root.addWidget(self.tip)

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search YouTube, for example: lofi study music")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.do_search)
        self.b_search = QPushButton("Search")
        self.b_search.setObjectName("primary")
        self.b_search.clicked.connect(lambda checked=False: self.do_search())
        row.addWidget(self.search, 1)
        row.addWidget(self.b_search)
        root.addLayout(row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(lambda item: self.play_item(item))
        root.addWidget(self.list, 1)

        self.now = QLabel("Nothing is playing.")
        self.now.setWordWrap(True)
        self.now.setStyleSheet("font-weight: bold;")
        root.addWidget(self.now)

        seek_row = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setEnabled(False)
        self.seek.sliderMoved.connect(self.s.seek_to)
        self.seek.sliderReleased.connect(lambda: self.s.seek_to(self.seek.value()))
        self.time = QLabel("0:00 / 0:00")
        self.time.setMinimumWidth(110)
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.time)
        root.addLayout(seek_row)

        ctl = QHBoxLayout()
        self.b_prev = QPushButton("⏮ Previous")
        self.b_play = QPushButton("▶ Play")
        self.b_play.setObjectName("primary")
        self.b_stop = QPushButton("⏹ Stop")
        self.b_next = QPushButton("Next ⏭")
        self.b_prev.clicked.connect(lambda checked=False: self.s.prev())
        self.b_play.clicked.connect(lambda checked=False: self.play_or_pause())
        self.b_stop.clicked.connect(lambda checked=False: self.s.stop())
        self.b_next.clicked.connect(lambda checked=False: self.s.next())
        for b in (self.b_prev, self.b_play, self.b_stop, self.b_next):
            ctl.addWidget(b)
        ctl.addStretch()
        root.addLayout(ctl)

        vol = QHBoxLayout()
        vol.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(self.s.volume())
        self.volume.setMaximumWidth(220)
        self.volume.valueChanged.connect(self.s.set_volume)
        self.auto = QCheckBox("Play the next result when a song ends")
        self.auto.setChecked(bool(self.s.opt("youtube_autonext", True)))
        self.auto.toggled.connect(lambda v: self.s.set_opt("youtube_autonext", bool(v)))
        b_close = QPushButton("Close")
        b_close.clicked.connect(lambda checked=False: self.hide())
        vol.addWidget(self.volume)
        vol.addSpacing(12)
        vol.addWidget(self.auto)
        vol.addStretch()
        vol.addWidget(b_close)
        root.addLayout(vol)
        self.refresh_all()

    # -- actions --------------------------------------------------------------
    def do_search(self):
        self.s.search(self.search.text())

    def play_item(self, item):
        row = self.list.row(item)
        if row >= 0:
            self.s.play_index(row)

    def play_or_pause(self):
        if self.s.has_audio():
            self.s.toggle_pause()
        elif self.list.currentRow() >= 0:
            self.s.play_index(self.list.currentRow())
        elif self.s.queue:
            self.s.play_index(0)

    # -- showing what the service knows ----------------------------------------
    def set_status(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet("color: #c0392b;" if error else "")

    def refresh_all(self):
        self.refresh_tip()
        self.refresh_results()
        self.refresh_now()

    def refresh_tip(self):
        missing = []
        if yt_dlp is None:
            missing.append("yt-dlp is not installed. Run in a terminal:  pip install -U \"yt-dlp[default]\"")
        if QMediaPlayer is None:
            missing.append("This PySide6 has no sound support (QtMultimedia).")
        if yt_dlp is not None and not js_runtimes():
            missing.append("Tip: YouTube needs Deno or Node.js to be installed (and in the PATH), "
                           "or some songs will not download.")
        self.tip.setText("\n".join(missing))
        self.tip.setVisible(bool(missing))

    def refresh_results(self):
        keep = self.list.currentRow()
        self.list.clear()
        for i, it in enumerate(self.s.queue):
            mark = "▶  " if i == self.s.index and self.s.has_audio() else ""
            row = QListWidgetItem("%s%s\n%s   ·   %s" % (
                mark, it["title"], it["channel"] or "YouTube", fmt_time(it["duration"])))
            if mark:
                font = row.font()
                font.setBold(True)
                row.setFont(font)
            self.list.addItem(row)
        if 0 <= keep < self.list.count():
            self.list.setCurrentRow(keep)

    def refresh_now(self):
        s = self.s
        cur = s.current
        if cur is None:
            self.now.setText("Loading: %s" % short(s.loading["title"], 70) if s.loading else "Nothing is playing.")
        else:
            state = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped"}.get(s.state(), "")
            self.now.setText("%s: %s" % (state, short(cur["title"], 80)))
        self.b_play.setText("⏸ Pause" if s.state() == "playing" else "▶ Play")
        busy = s.searching
        self.b_search.setEnabled(not busy and yt_dlp is not None)
        self.b_search.setText("Searching..." if busy else "Search")
        has = bool(s.queue)
        self.b_prev.setEnabled(has)
        self.b_next.setEnabled(has)

    def set_progress(self, pos_ms, dur_ms):
        self.seek.setEnabled(dur_ms > 0)
        if self.seek.maximum() != dur_ms:
            self.seek.setRange(0, max(0, dur_ms))
        if not self.seek.isSliderDown():
            self.seek.setValue(max(0, min(pos_ms, max(0, dur_ms))))
        self.time.setText("%s / %s" % (fmt_time(pos_ms // 1000), fmt_time(dur_ms // 1000)))


# ----------------------------------------------------------------------
# the service that Main_file.pyw talks to
# ----------------------------------------------------------------------
class YouTubeService(QObject):
    """Main_file.pyw creates one. cat must have: saved (dict), save_settings(), notify(), wake(),
    features (for the speech bubble, may be None), assistant.dnd, paused, big_mode."""
    _found = Signal(int, object, str)              # search id, {"items": [...], "skipped": n}, error
    _progress = Signal(int, int)                   # request id, percent
    _fetched = Signal(int, object, str, str)       # request id, item, file path, error

    def __init__(self, cat, base_dir, window_style):
        super().__init__()
        self.cat = cat
        self.cache = os.path.join(base_dir, CACHE_DIR)
        self.style = window_style
        self.window = None
        self.player = None
        self.audio = None
        self.queue = []                    # the results of the last search
        self.index = -1                    # where the current song is in the queue (-1 = not in it)
        self.current = None                # the song that is loaded in the player
        self.current_path = ""
        self.loading = None                # the song that is being fetched
        self.streaming = False             # True while the loaded song plays straight from YouTube
        self._no_stream = set()            # songs where streaming did not work (they are downloaded)
        self.searching = False
        self._req = 0                      # id of the current download
        self._sreq = 0                     # id of the current search
        self._last_pct = -1
        self._last_emit = 0.0
        self.status_action = None
        self.pause_action = None
        # cat reactions
        self._front_since = 0.0            # when YouTube came to the front (0 = it is not in front)
        self._hello_done = False
        self._last_hello = 0.0
        self._last_seen = 0.0
        self._watch_secs = 0.0
        self._last_rest = 0.0
        self._last_phase = None            # "singing" / "dance" / None: what the music made the cat do last
        self._demo_t0 = 0.0                # "Test: sing now" runs from this time (perf_counter) ...
        self._demo_until = 0.0             # ... until this time
        self._other_say_until = 0.0        # another message (hello, singing) is on screen until then
        self._found.connect(self._on_found)
        self._progress.connect(self._on_progress)
        self._fetched.connect(self._on_fetched)
        self.watch_timer = QTimer(cat)
        self.watch_timer.setInterval(WATCH_POLL_MS)
        self.watch_timer.timeout.connect(self._poll)
        self.watch_timer.start()
        self.np_timer = QTimer(cat)                 # the "Now playing" message is refreshed every second
        self.np_timer.setInterval(1000)
        self.np_timer.timeout.connect(self._now_playing)
        self.np_timer.start()
        self.prune_cache()

    # -- settings -----------------------------------------------------------------
    def opt(self, key, default):
        return self.cat.saved.get(key, default)

    def set_opt(self, key, value):
        self.cat.saved[key] = value
        self.cat.save_settings()

    def volume(self):
        try:
            return max(0, min(100, int(self.opt("youtube_volume", DEFAULT_VOLUME))))
        except (TypeError, ValueError):
            return DEFAULT_VOLUME

    def set_volume(self, value):
        value = max(0, min(100, int(value)))
        self.cat.saved["youtube_volume"] = value
        if self.audio is not None:
            self.audio.setVolume(value / 100.0)
        self._save_soon()

    def _save_soon(self):
        """The volume slider fires many times: ask the cat to save once, a moment later."""
        timer = getattr(self.cat, "save_timer", None)
        if timer is not None:
            timer.start()
        else:
            self.cat.save_settings()

    # -- the window -----------------------------------------------------------------
    def open_window(self):
        if self.window is None:
            self.window = YouTubeWindow(self, self.style)
        self.window.refresh_all()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.search.setFocus()
        self.window.search.selectAll()

    def _ui(self):
        """The window if it exists (it is made when it is first opened)."""
        return self.window

    def _status(self, text, error=False):
        w = self._ui()
        if w is not None:
            w.set_status(text, error)
        self.update_menu()

    def _refresh(self):
        w = self._ui()
        if w is not None:
            w.refresh_results()
            w.refresh_now()
        self.update_menu()

    # -- searching -------------------------------------------------------------------
    def search(self, text):
        text = " ".join(str(text).split())
        if not text:
            return
        if not self._can_work():
            return
        self._sreq += 1
        self.searching = True
        self._status("Searching for \"%s\"..." % short(text, 50))
        self._refresh()
        threading.Thread(target=self._search_worker, args=(self._sreq, text), daemon=True).start()

    def _can_work(self):
        if yt_dlp is None:
            self._status("yt-dlp is not installed. Run in a terminal:  pip install -U \"yt-dlp[default]\"", True)
            return False
        if QMediaPlayer is None:
            self._status("This PySide6 has no sound support (QtMultimedia): %s" % _MM_ERROR, True)
            return False
        return True

    @staticmethod
    def _item(entry):
        vid = str(entry.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return None
        duration = entry.get("duration")
        live = entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming")
        if live or not isinstance(duration, (int, float)) or duration <= 0 or duration > MAX_MINUTES * 60:
            return "live"          # live streams have no end, and very long videos are too big to download
        return {"id": vid, "title": str(entry.get("title") or "(no title)"),
                "channel": str(entry.get("channel") or entry.get("uploader") or ""),
                "duration": int(duration), "url": "https://www.youtube.com/watch?v=" + vid}

    def _search_worker(self, sreq, text):
        log = _Quiet()
        try:
            vid = video_id_from(text)
            if vid:                                         # a pasted link: just that one video
                opts = ydl_options(log, skip_download=True)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info("https://www.youtube.com/watch?v=" + vid, download=False,
                                            process=False)
                entries = [info or {}]
            else:
                opts = ydl_options(log, skip_download=True, extract_flat="in_playlist")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info("ytsearch%d:%s" % (SEARCH_RESULTS + 6, text), download=False)
                entries = list((info or {}).get("entries") or [])
            items, skipped = [], 0
            for e in entries:
                it = self._item(e) if isinstance(e, dict) else None
                if it == "live":
                    skipped += 1
                elif it is not None and len(items) < SEARCH_RESULTS:
                    items.append(it)
            self._found.emit(sreq, {"items": items, "skipped": skipped}, "")
        except Exception as err:
            self._found.emit(sreq, None, clean_error(log.last_error or err))

    def _on_found(self, sreq, data, err):
        if sreq != self._sreq:
            return
        self.searching = False
        if data is None:
            self._status(err, True)
            self._refresh()
            return
        items = data["items"]
        self.queue = items
        self.index = next((i for i, it in enumerate(items)
                           if self.current is not None and it["id"] == self.current["id"]), -1)
        if not items:
            msg = "Nothing found. Try other words."
            if data["skipped"]:
                msg += " (Live streams and videos over %d minutes are left out.)" % MAX_MINUTES
            self._status(msg, True)
        else:
            msg = "%d result%s. Double-click a song to play it." % (len(items), "" if len(items) == 1 else "s")
            if data["skipped"]:
                msg += " Live streams and videos over %d minutes are left out." % MAX_MINUTES
            self._status(msg)
        self._refresh()
        w = self._ui()
        if w is not None and items:
            w.list.setFocus()
            w.list.setCurrentRow(0)

    # -- getting the sound -------------------------------------------------------------
    def _cached(self, vid):
        """The finished sound file of a video, or ''."""
        best, best_t = "", -1.0
        for path in glob.glob(os.path.join(glob.escape(self.cache), glob.escape(vid) + ".*")):
            if is_temp_file(path):
                continue
            try:
                t = os.path.getmtime(path)
            except OSError:
                continue
            if t > best_t:
                best, best_t = path, t
        return best

    def play_index(self, i):
        if not (0 <= i < len(self.queue)) or not self._can_work():
            return
        self.index = i
        self._play_item(self.queue[i])

    def _play_item(self, item):
        self._req += 1
        req = self._req
        self._stop_player()
        self.current, self.current_path, self.streaming = None, "", False
        self.loading = item
        self._last_pct = -1
        cached = self._cached(item["id"])
        if cached:                                              # downloaded before: starts at once
            self._fetched.emit(req, item, cached, "")
        elif item["id"] in self._no_stream:                     # streaming failed before: download it
            self._status("Downloading \"%s\"..." % short(item["title"], 50))
            threading.Thread(target=self._download_worker, args=(req, item), daemon=True).start()
        else:                                                   # normal way: ask for the link, then stream
            self._status("Asking YouTube for \"%s\"...  (a few seconds)" % short(item["title"], 45))
            threading.Thread(target=self._stream_worker, args=(req, item), daemon=True).start()
        self._refresh()

    def _stream_worker(self, req, item):
        """Get the direct sound link of a video (no download). If there is none, download instead."""
        log = _Quiet()
        try:
            opts = ydl_options(log, format="bestaudio[ext=m4a]/bestaudio", skip_download=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item["url"], download=False) or {}
        except Exception as err:
            if req == self._req:
                self._fetched.emit(req, item, "", clean_error(log.last_error or err))
            return
        if req != self._req:
            return
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            self._fetched.emit(req, item, "", "This is a live stream. I can only play normal videos.")
            return
        if (info.get("duration") or 0) > MAX_MINUTES * 60:
            self._fetched.emit(req, item, "", "This video is longer than %d minutes. Try a shorter one." % MAX_MINUTES)
            return
        url = str(info.get("url") or "")
        if url.startswith(("http://", "https://")) and info.get("protocol") in ("https", "http", None):
            self._fetched.emit(req, item, url, "")
        else:
            self._download_worker(req, item)                    # no plain link: download it (we are in the worker thread)

    def _download_worker(self, req, item):
        log = _Quiet()
        skip = {"why": ""}

        def match(info, *args, **kwargs):
            if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
                skip["why"] = "This is a live stream. I can only play normal videos."
                return "live"
            if (info.get("duration") or 0) > MAX_MINUTES * 60:
                skip["why"] = "This video is longer than %d minutes. Try a shorter one." % MAX_MINUTES
                return "long"
            return None

        def hook(d):
            if req != self._req:
                raise yt_dlp.utils.DownloadCancelled("another song was chosen")
            if d.get("status") != "downloading":
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            now = time.time()
            if total and now - self._last_emit >= 0.25:
                self._last_emit = now
                self._progress.emit(req, int(100 * done / total))

        try:
            os.makedirs(self.cache, exist_ok=True)
            opts = ydl_options(log, format="bestaudio[ext=m4a]/bestaudio",
                               paths={"home": self.cache}, outtmpl="%(id)s.%(ext)s",
                               progress_hooks=[hook], match_filter=match, continuedl=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item["url"], download=True)
            path = ""
            for rd in (info or {}).get("requested_downloads") or []:
                fp = rd.get("filepath") or rd.get("_filename") or ""
                if fp and os.path.exists(fp):
                    path = fp
            path = path or self._cached(item["id"])
            if not path:
                self._fetched.emit(req, item, "", skip["why"] or clean_error(log.last_error or "No sound file."))
                return
            self._fetched.emit(req, item, path, "")
        except Exception as err:
            if req == self._req:
                self._fetched.emit(req, item, "", clean_error(log.last_error or err))

    def _on_progress(self, req, pct):
        if req != self._req or self.loading is None or pct == self._last_pct:
            return
        self._last_pct = pct
        self._status("Getting the sound of \"%s\"...  %d%%" % (short(self.loading["title"], 40), pct))

    def _on_fetched(self, req, item, path, err):
        if req != self._req:
            return
        self.loading = None
        if err or not path:
            self._status(err or "I could not get this song.", True)
            self._refresh()
            return
        if not self._ensure_player():
            return
        streaming = path.startswith(("http://", "https://"))
        self.current, self.current_path, self.streaming = item, ("" if streaming else path), streaming
        self._status("Playing. Double-click another song to change it.")
        self.player.setSource(QUrl.fromEncoded(path.encode("ascii", "ignore")) if streaming
                              else QUrl.fromLocalFile(path))
        self.player.play()
        if self.current is None:                    # the player refused the file (the error is already shown)
            return
        if streaming:                               # if it has not started after a while, download it instead
            QTimer.singleShot(STREAM_WAIT_SECONDS * 1000, lambda: self._stream_watchdog(req))
        self._last_phase = None                     # the singing and dancing start from the beginning
        self.say("Now playing: %s" % short(item["title"], 45), 6.0, "singing")
        self.prune_cache()
        self._refresh()

    # -- the player ---------------------------------------------------------------------
    def _ensure_player(self):
        if self.player is not None:
            return True
        if QMediaPlayer is None:
            self._status("This PySide6 has no sound support (QtMultimedia): %s" % _MM_ERROR, True)
            return False
        try:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(self.volume() / 100.0)
            self.player.setAudioOutput(self.audio)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_position)
            self.player.playbackStateChanged.connect(lambda state: self._refresh())
            self.player.mediaStatusChanged.connect(self._on_media_status)
            self.player.errorOccurred.connect(self._on_player_error)
            return True
        except Exception as err:
            self.player = self.audio = None
            self._status("The sound player could not start (%s)." % err, True)
            return False

    def state(self):
        """"playing", "paused" or "stopped" (also when nothing is loaded)."""
        if self.player is None or self.current is None:
            return "stopped"
        st = self.player.playbackState()
        if st == QMediaPlayer.PlaybackState.PlayingState:
            return "playing"
        if st == QMediaPlayer.PlaybackState.PausedState:
            return "paused"
        return "stopped"

    def has_audio(self):
        return self.current is not None

    def _stop_player(self):
        if self.player is not None:
            try:
                self.player.stop()
                self.player.setSource(QUrl())      # let go of the file (Windows cannot delete an open file)
            except Exception:
                pass
        w = self._ui()
        if w is not None:
            w.set_progress(0, 0)

    def toggle_pause(self):
        if self.player is None or self.current is None:
            self.open_window()
            return
        st = self.state()
        if st == "playing":
            self.player.pause()
        else:
            if st == "stopped" and self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()
        self._refresh()

    def stop(self):
        self._req += 1                              # also cancels a download in progress
        self.loading = None
        if self.player is not None and self.current is not None:
            self.player.stop()
            self.player.setPosition(0)
        self._status("Stopped.")
        self._refresh()

    def next(self):
        if self.queue:
            self.play_index(self.index + 1 if 0 <= self.index < len(self.queue) - 1 else 0)

    def prev(self):
        if self.queue:
            self.play_index(self.index - 1 if self.index > 0 else len(self.queue) - 1)

    def seek_to(self, ms):
        if self.player is not None and self.current is not None:
            self.player.setPosition(int(ms))

    def _on_position(self, *args):
        w = self._ui()
        if w is not None and self.player is not None:
            w.set_progress(int(self.player.position()), int(self.player.duration()))

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._on_player_error(None, "the file is damaged or has a sound format I cannot play")
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self.opt("youtube_autonext", True) and 0 <= self.index < len(self.queue) - 1:
            self.play_index(self.index + 1)
        else:
            self._status("The song has ended.")
            self._refresh()

    def _on_player_error(self, error, text=""):
        if self.current is None:
            return                                  # this problem was already handled
        if self.streaming:                          # streaming failed: download the song instead
            item, req = self.current, self._req
            self.current, self.current_path, self.streaming = None, "", False
            QTimer.singleShot(0, lambda: self._fallback(item, req))
            return
        bad = self.current_path
        self.current, self.current_path = None, ""
        self._status("I could not play this sound (%s). Try another song." % (text or "unknown error"), True)
        self._refresh()
        QTimer.singleShot(0, lambda: self._drop_bad_file(bad))   # clean up after the player has finished its signal

    def _fallback(self, item, req):
        if req != self._req or self.current is not None:
            return                                  # another song was chosen in the meantime
        self._no_stream.add(item["id"])
        self._play_item(item)                       # this time it is downloaded

    def _stream_watchdog(self, req):
        """A streamed song that is still at 0:00 after STREAM_WAIT_SECONDS: download it instead."""
        if (req != self._req or not self.streaming or self.current is None or self.player is None
                or self.state() == "paused" or self.player.position() >= 300):
            return
        item = self.current
        self.current, self.current_path, self.streaming = None, "", False
        self._fallback(item, req)

    def _drop_bad_file(self, path):
        """A damaged download must not be played again from the cache."""
        if self.current is not None:
            return                                  # another song was started in the meantime
        self._stop_player()
        if path and os.path.normcase(os.path.abspath(os.path.dirname(path))) == \
                os.path.normcase(os.path.abspath(self.cache)):
            self._remove(path)

    # -- cat reactions --------------------------------------------------------------------
    def say(self, text, seconds=5.0, mood=None, badge="YOUTUBE"):
        if getattr(self.cat, "big_mode", False) or getattr(self.cat, "paused", False):
            return
        self._other_say_until = time.time() + seconds
        f = getattr(self.cat, "features", None)
        if f is not None:
            f.react(text, mood, seconds, None, badge, None)
        else:
            self.cat.wake()

    def _now_playing(self):
        """While a song plays: keep a message with its name and time in the cat's bubble."""
        if (not self.opt("youtube_bubble", True) or self.state() != "playing" or self.player is None
                or time.time() < self._other_say_until or not self._cat_free()
                or getattr(self.cat, "big_mode", False)):
            return
        f = getattr(self.cat, "features", None)
        if f is None:
            return
        text = "\u266A %s\n%s / %s" % (short(self.current["title"], 48),
                                        fmt_time(int(self.player.position()) // 1000),
                                        fmt_time(int(self.player.duration()) // 1000))
        f.say(text, 2.5, "NOW PLAYING")             # a few seconds long, so it fades soon after the music stops

    def _cat_free(self):
        f = getattr(self.cat, "features", None)
        if f is not None:
            try:
                return bool(f._free_for_event())
            except Exception:
                pass
        return not getattr(self.cat, "paused", False) and not getattr(self.cat.assistant, "dnd", False)

    def _block_reason(self):
        """Why the cat stays quiet right now, in words ("" = nothing stops it).
        These are the same things that _cat_free() checks."""
        cat = self.cat
        if getattr(cat, "paused", False):
            return "the cat is paused"
        if getattr(cat, "big_mode", False):
            return "the Cat Arcade is open"
        a = getattr(cat, "assistant", None)
        if a is not None:
            if getattr(a, "dnd", False):
                return "Do not disturb is switched on in the tray menu"
            try:
                if a.busy():
                    return "a reminder or chat bubble is open"
            except Exception:
                pass
            try:
                if a.rps.is_active():
                    return "a game is running"
            except Exception:
                pass
        if getattr(cat, "feed", None) is not None:
            return "the cat is eating"
        return ""

    # -- singing to the music --------------------------------------------------------
    def music_mood(self, now):
        """What the music makes the cat do right now: "singing" or None.
        Main_file.pyw asks this every frame (now = time.perf_counter()). The cat only sings along
        while a song plays. It never dances to the music."""
        if now < self._demo_until:                                  # "Test: sing now"
            return "singing"
        if not self.opt("youtube_sing", True) or self.state() != "playing" or not self._cat_free():
            return None
        return "singing"

    def keep_out(self):
        """True while the cat must stay up because of the music (Main_file.pyw asks this every frame)."""
        if time.perf_counter() < self._demo_until:
            return True
        return (self.state() == "playing" and bool(self.opt("youtube_sing", True))
                and self._cat_free())

    def test_music(self):
        """Tray > "Test: sing now": you see at once what the cat does, without any music."""
        now = time.perf_counter()
        self._demo_t0, self._demo_until = now, now + TEST_SECONDS
        self._last_phase = None
        text = "Test: I sing along for a moment!"
        reason = self._block_reason()
        if reason:
            text += "\n(With real music I would stay quiet now, because %s.)" % reason
        self._report(text, None, TEST_SECONDS - 1.0)

    # -- YouTube open in the browser ----------------------------------------------------------------
    def _report(self, text, mood=None, seconds=9.0):
        """Show a test message: in the cat's bubble (or in a box when the cat cannot show bubbles now)."""
        if getattr(self.cat, "big_mode", False) or getattr(self.cat, "paused", False):
            QMessageBox.information(None, "YouTube music", text)
        else:
            self.say(text, seconds, mood, "TEST")

    def test_react(self):
        """Tray > "Test: what does the cat see?": switch to your YouTube window, the cat looks a few
        seconds later and tells you what it saw (the tray menu itself is a window too, so it cannot be
        looked at straight away)."""
        self._report("Switch to your YouTube window now. I will look in %d seconds..." % TEST_SECONDS,
                     None, float(TEST_SECONDS))
        QTimer.singleShot(TEST_SECONDS * 1000, self._test_react_now)

    def _test_react_now(self):
        title, pid = foreground_title()
        mine = pid == os.getpid()
        on_youtube = bool(title) and not mine and bool(_YT_TITLE.search(title))
        if not title:
            lines = ["I could not read the title of the window in front."]
        elif mine:
            lines = ["The window in front is one of my own windows. Switch to your browser next time."]
        else:
            lines = ['The window in front is called: "%s".' % short(title, 70)]
            lines.append("That is YouTube. I react to it!" if on_youtube
                         else 'There is no word "YouTube" in that title, so I do not react.')
        if not self.opt("youtube_react", True):
            lines.append('But "Cat reacts to YouTube" is switched off in the menu.')
        reason = self._block_reason()
        if reason:
            lines.append("Normally I would stay quiet now, because %s." % reason)
        self._report("\n".join(lines), "happy" if on_youtube else "confused", 10.0)

    def _hello(self, title):
        """The cat says hello because YouTube came to the front."""
        text, mood = random.choice(HELLO_LINES)
        name = video_name(title)
        if name and random.random() < 0.5:
            text, mood = 'Ooh, "%s"! %s' % (short(name, 40), random.choice(("Enjoy!", "Nice!", "Have fun!"))), "happy"
        self.say(text, 5.0, mood)

    def _poll(self):
        now = time.time()
        if not self.opt("youtube_react", True):
            self._front_since, self._hello_done = 0.0, False
            return
        title, pid = foreground_title()
        on_youtube = bool(title) and pid != os.getpid() and bool(_YT_TITLE.search(title))
        if not on_youtube:
            self._front_since, self._hello_done = 0.0, False
            return
        if now - self._last_seen > WATCH_RESET_SECONDS:
            self._watch_secs = 0.0                  # a new watching session
        self._last_seen = now
        self._watch_secs += WATCH_POLL_MS / 1000.0
        if not self._front_since:
            self._front_since = now
        if not self._cat_free():
            return                                  # try again at the next look (the reason may be gone by then)
        if not self._hello_done and now - self._front_since >= WATCH_CONFIRM_SECONDS:
            self._hello_done = True                 # one decision for every visit to YouTube
            if now - self._last_hello >= HELLO_COOLDOWN:
                self._last_hello = now
                self._hello(title)
        elif self._watch_secs >= REST_EYES_MINUTES * 60 and now - self._last_rest >= REST_COOLDOWN:
            self._last_rest = now
            self._watch_secs = 0.0
            self.say(REST_TEXT, 9.0, "yawn", "REST YOUR EYES")
            self.cat.notify("Peeking Cat - rest your eyes", REST_TEXT)   # also visual, for deaf users

    # -- cache -------------------------------------------------------------------------------
    def prune_cache(self):
        """Keep the newest CACHE_KEEP sound files, remove old half-finished downloads."""
        try:
            files = [p for p in glob.glob(os.path.join(glob.escape(self.cache), "*")) if os.path.isfile(p)]
        except OSError:
            return
        now = time.time()
        sounds = []
        for p in files:
            try:
                age = now - os.path.getmtime(p)
            except OSError:
                continue
            if is_temp_file(p):
                if age > 3600 and p != self.current_path:
                    self._remove(p)
            else:
                sounds.append((os.path.getmtime(p), p))
        sounds.sort(reverse=True)
        for _, p in sounds[CACHE_KEEP:]:
            if p != self.current_path:
                self._remove(p)

    @staticmethod
    def _remove(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def clear_cache(self):
        files = [p for p in glob.glob(os.path.join(glob.escape(self.cache), "*")) if os.path.isfile(p)]
        if not files:
            QMessageBox.information(None, "YouTube music", "There are no downloaded songs.")
            return
        size = sum(os.path.getsize(p) for p in files if os.path.exists(p)) / (1024.0 * 1024.0)
        if QMessageBox.question(None, "YouTube music", "Delete %d downloaded song%s (%.0f MB)?\n"
                                "The music will stop." % (len(files), "" if len(files) == 1 else "s", size)) \
                != QMessageBox.StandardButton.Yes:
            return
        self._req += 1
        self.loading = None
        self._stop_player()
        self.current, self.current_path, self.streaming = None, "", False
        gone = sum(1 for p in files if self._remove(p))
        self._status("Deleted %d file%s." % (gone, "" if gone == 1 else "s"))
        self._refresh()

    # -- tray menu -----------------------------------------------------------------------------
    def add_menu(self, menu, add):
        ym = menu.addMenu("YouTube music")
        self.status_action = ym.addAction("")
        self.status_action.setEnabled(False)
        add(ym, "Search and play...", self.open_window)
        self.pause_action = add(ym, "Pause", self.toggle_pause)
        add(ym, "Next song", self.next)
        add(ym, "Previous song", self.prev)
        add(ym, "Stop", self.stop)
        ym.addSeparator()
        for text, key in (("Cat shows the song name", "youtube_bubble"), ("Cat sings along", "youtube_sing"),
                          ("Cat reacts to YouTube", "youtube_react")):
            act = ym.addAction(text)
            act.setCheckable(True)
            act.setChecked(bool(self.opt(key, True)))
            act.toggled.connect(lambda value, k=key: self.set_opt(k, bool(value)))
        ym.addSeparator()
        add(ym, "Delete downloaded songs...", self.clear_cache)
        ym.aboutToShow.connect(self.update_menu)
        self.update_menu()
        return ym

    def update_menu(self):
        if self.status_action is None:
            return
        if self.loading is not None:
            text = "Loading: " + short(self.loading["title"], 36)
        elif self.current is not None:
            text = {"playing": "Playing: ", "paused": "Paused: "}.get(self.state(), "Stopped: ") + short(self.current["title"], 34)
        else:
            text = "Nothing is playing"
        self.status_action.setText(text)
        if self.pause_action is not None:
            self.pause_action.setText("Pause" if self.state() == "playing" else "Play")

    # -- quit ----------------------------------------------------------------------------------------
    def shutdown(self):
        """Called by Main_file.pyw when the program ends."""
        self._req += 1
        self._sreq += 1
        try:
            self.watch_timer.stop()
            self.np_timer.stop()
            if self.player is not None:
                self.player.stop()
        except Exception:
            pass
