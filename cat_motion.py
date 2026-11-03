"""
cat_motion.py - pick the cat up, throw it, let it sit on top of a window
=========================================================================
* Press on the cat and drag: you carry it around (it dangles and looks surprised).
* Let go: it falls. If it lands on the top edge of a window, it sits there exactly like it
  sits on the taskbar: it peeks out from behind the window's top edge (same SHOW_FRACTION as
  at home) and its paws hang over the title bar. Move that window and the cat rides along.
  If the window is closed, minimised, maximised or covered, the cat falls down again.
* If it falls onto the taskbar it is home again, at the new place (the place is remembered).
* Click the cat = pet it.  Double-click a sitting cat = it jumps down to the taskbar.
  Right-click the cat = the tray menu.
* Only the cat's body catches the mouse. Everywhere else your clicks go through as before.
  Tray > Play with the cat > "Cat can be picked up" switches this off completely.
"""
import math
import os
import sys
import time
from collections import deque

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QCursor, QGuiApplication

GRAVITY = 3200.0              # pixels per second per second
AIR_DRAG = 1.2                # sideways slowing down while falling
WALL_BOUNCE = 0.45            # how much speed is kept when bouncing off a screen edge
MAX_THROW = 2600.0            # fastest throw (pixels per second)
DRAG_START = 6                # pixels the mouse must move before a press becomes a drag
EDGE_MARGIN = 14              # the cat's middle must be this far inside a window to sit on it
HIT_ALPHA = 40                # a cat pixel counts as "body" from this opacity (0..255)
NAP_AFTER = 25.0              # a sitting cat falls asleep after this many idle seconds

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _MY_PID = os.getpid()

SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
                "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"}


# ----------------------------------------------------------------------
# Windows helpers (they return safe "nothing" answers on other systems)
# ----------------------------------------------------------------------
def set_click_through(widget, on):
    """on=True: mouse clicks pass through the window (like before). on=False: the window gets them."""
    if sys.platform != "win32":
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
        ex = _user32.GetWindowLongW(hwnd, -20)                 # GWL_EXSTYLE
        new = (ex | 0x20) if on else (ex & ~0x20)              # WS_EX_TRANSPARENT
        if new != ex:
            _user32.SetWindowLongW(hwnd, -20, new)
    except Exception:
        pass


def phys_to_logical(px, py):
    """Windows gives window positions in real screen pixels; Qt works in scaled pixels."""
    screens = QGuiApplication.screens()
    best, best_dist = None, None
    for s in screens:
        g = s.geometry()
        d = s.devicePixelRatio() or 1.0
        right, bottom = g.x() + g.width() * d, g.y() + g.height() * d
        if g.x() <= px < right and g.y() <= py < bottom:
            return g.x() + (px - g.x()) / d, g.y() + (py - g.y()) / d
        # a point just outside every screen (e.g. the hidden border of a maximised window):
        # use the nearest screen, measured from its native-pixel rectangle
        dx = max(g.x() - px, 0, px - right)
        dy = max(g.y() - py, 0, py - bottom)
        dist = dx * dx + dy * dy
        if best_dist is None or dist < best_dist:
            best, best_dist = s, dist
    if best is None:
        return float(px), float(py)
    g = best.geometry()
    d = best.devicePixelRatio() or 1.0
    return g.x() + (px - g.x()) / d, g.y() + (py - g.y()) / d


def _rect_of(hwnd):
    r = wintypes.RECT()
    if _dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:   # visible frame
        if not _user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
    if r.right - r.left < 60 or r.bottom - r.top < 40:
        return None
    x1, y1 = phys_to_logical(r.left, r.top)
    x2, y2 = phys_to_logical(r.right, r.bottom)
    return QRectF(x1, y1, x2 - x1, y2 - y1)


def _cloaked(hwnd):
    val = wintypes.DWORD(0)
    try:
        _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(val), ctypes.sizeof(val))   # DWMWA_CLOAKED
    except Exception:
        return False
    return bool(val.value)


def window_rect(hwnd):
    """The rectangle of a window if it is still there and showing, else None."""
    if sys.platform != "win32" or hwnd is None:
        return None
    try:
        h = wintypes.HWND(hwnd)
        if not _user32.IsWindow(h) or not _user32.IsWindowVisible(h) or _user32.IsIconic(h) or _cloaked(h):
            return None
        return _rect_of(h)
    except Exception:
        return None


def list_windows():
    """Normal windows of other programs, the one in front first: [(hwnd, QRectF), ...]."""
    if sys.platform != "win32":
        return []
    found = []

    def callback(hwnd, lparam):
        try:
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            if _user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            ex = _user32.GetWindowLongW(hwnd, -20)
            if (ex & 0x80) and not (ex & 0x40000):            # tool window (not an app window)
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == _MY_PID:                          # our own windows (cat, notes, bubbles)
                return True
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in SKIP_CLASSES or _cloaked(hwnd):
                return True
            rect = _rect_of(hwnd)
            if rect is not None:
                found.append((int(hwnd), rect))
        except Exception:
            pass
        return True
    try:
        _user32.EnumWindows(_ENUM_PROC(callback), 0)
    except Exception:
        return []
    return found


def covered(windows, index, x, y):
    """True if a window in front of windows[index] covers the point (x, y)."""
    for _, r in windows[:index]:
        if r.contains(x, y):
            return True
    return False


# ----------------------------------------------------------------------
class CatMover:
    """Main_file.pyw creates one and calls press / move / release / double_click from the cat's
    mouse events, update_input() and tick() every frame."""

    def __init__(self, cat):
        self.cat = cat
        self.place = "home"           # "home", "drag", "fall" or "perch"
        self.cx = 0.0                 # middle of the cat (x) ...
        self.bottom = 0.0             # ... and the line its paws stand on (y)
        self.vx = self.vy = 0.0
        self.tilt = 0.0
        self.grab = None              # cursor offset from (cx, bottom) while dragging
        self.press_at = None
        self.samples = deque(maxlen=8)
        self.grab_t = 0.0
        self.land_t = -10.0
        self.perch_hwnd = None
        self.perch_dx = 0.0
        self.ignore_windows = False
        self.windows = []
        self.windows_t = 0.0
        self.through = None           # current click-through state (None = not set yet)
        self.ticks = 0
        self.list_windows = list_windows      # replaceable (tests)
        self.window_rect = window_rect

    # -- simple questions -------------------------------------------------------
    def enabled(self):
        return bool(self.cat.saved.get("pickup", True))

    def is_home(self):
        return self.place == "home"

    def in_air(self):
        return self.place in ("drag", "fall")

    def paws_visible(self):
        return self.place in ("home", "perch")

    def emotion(self, now):
        """The face the cat should make because of being carried (None = no opinion)."""
        if self.place == "drag":
            return "surprised" if now - self.grab_t < 0.5 else "happy"
        if self.place == "fall" or now - self.land_t < 0.45:
            return "surprised"
        if self.place == "perch" and now - self.cat.last_move > NAP_AFTER:
            return "sleeping"
        return None

    def squash(self, now):
        """Vertical squash right after landing (1.0 = normal)."""
        k = (now - self.land_t) / 0.35
        if 0.0 <= k < 1.0:
            return 1.0 - 0.13 * math.sin(math.pi * k) * (1.0 - k)
        return 1.0

    def _screen_geo(self, x, y, available=False):
        s = QGuiApplication.screenAt(QPoint(int(x), int(y))) or QGuiApplication.primaryScreen()
        return (s.availableGeometry() if available else s.geometry()), s

    # -- the cat's window -----------------------------------------------------------
    def apply(self):
        """Put the cat's window where cx / bottom say (keeps working when the size changes)."""
        cat = self.cat
        w = cat.cat_w
        h = cat.cat_h + cat.pad + getattr(cat, "paw_drop", 0)
        x = int(round(self.cx - w / 2.0))
        y = int(round(self.bottom - cat.pad - cat.cat_h))
        if cat.geometry().getRect() != (x, y, w, h):
            cat.setGeometry(x, y, w, h)

    def hit(self, gpos):
        """Is the mouse on the cat's body (not on the see-through parts)?"""
        cat = self.cat
        img = getattr(cat, "hit_img", None)
        if img is None or cat.pos_ < 0.5:
            return False
        top = cat.pad + (1.0 - cat.pos_) * cat.cat_h
        ix = gpos.x() - cat.x()
        iy = gpos.y() - cat.y() - top
        if not (0 <= ix < img.width() and 0 <= iy < img.height()):
            return False
        if iy >= cat.pos_ * cat.cat_h:
            return False          # the part hidden behind the taskbar edge: clicks go to the taskbar
        return img.pixelColor(int(ix), int(iy)).alpha() >= HIT_ALPHA

    def update_input(self):
        """Every frame: the cat's body catches the mouse, everything else lets clicks through."""
        cat = self.cat
        self.ticks += 1
        want = (self.enabled() and not cat.paused and not getattr(cat, "big_mode", False)
                and (self.place == "drag" or self.hit(QCursor.pos())))
        through = not want
        if through != self.through or self.ticks % 60 == 0:
            self.through = through
            set_click_through(cat, through)
            cat.setCursor(Qt.CursorShape.ClosedHandCursor if self.place == "drag"
                          else Qt.CursorShape.OpenHandCursor)

    # -- mouse ------------------------------------------------------------------------
    def press(self, gpos):
        if not self.enabled() or getattr(self.cat, "big_mode", False):
            return
        self.press_at = QPoint(gpos)

    def move(self, gpos):
        if self.press_at is None:
            return
        if self.place != "drag":
            if (gpos - self.press_at).manhattanLength() < DRAG_START:
                return
            self._start_drag(self.press_at)
        g, _ = self._screen_geo(gpos.x(), gpos.y())
        cat = self.cat
        self.cx = gpos.x() - self.grab[0]
        self.bottom = gpos.y() - self.grab[1]
        self.cx = max(g.x() + cat.cat_w * 0.25, min(self.cx, g.x() + g.width() - cat.cat_w * 0.25))
        self.bottom = max(g.y() + cat.cat_h * 0.5, min(self.bottom, g.y() + g.height() + cat.cat_h * 0.3))
        now = time.perf_counter()
        self.samples.append((now, self.cx, self.bottom))
        self.apply()

    def release(self, gpos):
        was_press = self.press_at is not None
        self.press_at = None
        if self.place == "drag":
            self._throw()
        elif was_press:
            self.cat.on_cat_clicked()

    def double_click(self):
        self.press_at = None
        if self.place == "perch":
            self.jump_down()
        elif self.place == "home":
            self.cat.do_meow_now()

    def _start_drag(self, at):
        cat = self.cat
        if self.place in ("home", "perch"):
            cat.pos_, cat.vel = 1.0, 0.0      # picked up: the whole cat comes out from behind the edge
        # Measure where the cat is BEFORE the stroll is stopped: stopping it moves the window back
        # to the home spot, and the cat would jump away from the mouse pointer.
        self.cx = cat.x() + cat.cat_w / 2.0
        self.bottom = cat.y() + cat.pad + cat.cat_h
        self.grab = (at.x() - self.cx, at.y() - self.bottom)
        self.place = "drag"
        features = getattr(cat, "features", None)
        if features is not None:
            features._end_walk(snap=True)          # reposition() now follows the mover (not home)
        self.grab_t = time.perf_counter()
        self.samples.clear()
        self.samples.append((self.grab_t, self.cx, self.bottom))
        cat.on_picked_up()
        self.update_input()

    def _throw(self):
        now = time.perf_counter()
        recent = [s for s in self.samples if now - s[0] <= 0.12]
        vx = vy = 0.0
        if len(recent) >= 2 and recent[-1][0] - recent[0][0] > 0.005:
            span = recent[-1][0] - recent[0][0]
            vx = (recent[-1][1] - recent[0][1]) / span
            vy = (recent[-1][2] - recent[0][2]) / span
        self.vx = max(-MAX_THROW, min(MAX_THROW, vx))
        self.vy = max(-MAX_THROW, min(MAX_THROW, vy))
        self._fall(ignore_windows=False, keep_speed=True)

    # -- falling / sitting ------------------------------------------------------------
    def _fall(self, ignore_windows=False, keep_speed=False):
        self.place = "fall"
        self.ignore_windows = ignore_windows
        if not keep_speed:
            self.vx = self.vy = 0.0
        self.perch_hwnd = None
        self.windows = [] if ignore_windows else self.list_windows()
        self.windows_t = time.perf_counter()

    def jump_down(self):
        """A sitting cat hops down to the taskbar (ignores windows on the way)."""
        if self.place != "perch":
            return
        self.vy = -650.0
        self.vx = 0.0
        self._fall(ignore_windows=True, keep_speed=True)

    def go_home(self):
        """Straight back to the saved place on the taskbar (Arcade, Pause, tray menu)."""
        if self.place == "home":
            return
        self.place = "home"
        self.tilt = 0.0
        self.press_at = None
        self.perch_hwnd = None
        self.cat.reposition()

    def tick(self, dt, now):
        """Returns True while the mover decides where the cat is (not at home)."""
        if self.place == "home":
            return False
        cat = self.cat
        target_tilt = 0.0
        if self.place == "drag":
            if len(self.samples) >= 2:
                (t0, x0, _), (t1, x1, _) = self.samples[-2], self.samples[-1]
                if now - t1 < 0.15 and t1 > t0:
                    target_tilt = max(-12.0, min(12.0, -(x1 - x0) / (t1 - t0) * 0.012))
            target_tilt += 3.0 * math.sin(now * 5.0)          # gentle dangling
        elif self.place == "fall":
            self._step_fall(dt, now)
            target_tilt = max(-12.0, min(12.0, self.vx * 0.008))
        elif self.place == "perch":
            self._step_perch(now)
        if self.place == "home":                              # landed on the taskbar just now
            return False
        self.tilt += (target_tilt - self.tilt) * min(1.0, dt * 10.0)
        if self.place == "perch":
            # Sitting on a window: peek out like at home on the taskbar (only SHOW_FRACTION of the
            # cat shows, the rest is hidden behind the window's top edge). Ease into it so the cat
            # settles down softly after landing instead of jumping.
            goal = cat.show_target()
            cat.pos_ += (goal - cat.pos_) * min(1.0, dt * 9.0)
            if abs(goal - cat.pos_) < 0.002:
                cat.pos_ = goal
            cat.vel = 0.0
        else:
            cat.pos_, cat.vel = 1.0, 0.0                      # carried / falling: the whole cat
        self.apply()
        return True

    def _step_fall(self, dt, now):
        cat = self.cat
        prev_bottom = self.bottom
        self.vy += GRAVITY * dt
        self.vx *= math.exp(-AIR_DRAG * dt)
        self.cx += self.vx * dt
        self.bottom += self.vy * dt
        g, screen = self._screen_geo(self.cx, self.bottom - cat.cat_h / 2.0)
        half = cat.cat_w / 2.0
        if self.cx - half < g.x():
            self.cx, self.vx = g.x() + half, abs(self.vx) * WALL_BOUNCE
        elif self.cx + half > g.x() + g.width():
            self.cx, self.vx = g.x() + g.width() - half, -abs(self.vx) * WALL_BOUNCE
        if self.bottom - cat.cat_h < g.y():
            self.bottom, self.vy = g.y() + cat.cat_h, max(0.0, self.vy)
        if self.vy <= 0:
            return
        ground = screen.availableGeometry().y() + screen.availableGeometry().height()
        if not self.ignore_windows:
            if now - self.windows_t > 0.25:
                self.windows = self.list_windows()
                self.windows_t = now
            for i, (hwnd, r) in enumerate(self.windows):
                top = r.top()
                if not (r.left() + EDGE_MARGIN <= self.cx <= r.right() - EDGE_MARGIN):
                    continue
                if not (prev_bottom - 2 <= top <= self.bottom):
                    continue
                if top - cat.cat_h < g.y() or top > ground - 30:
                    continue                                     # no room above it / too low
                if covered(self.windows, i, self.cx, top + 3):
                    continue
                self._land_on_window(hwnd, r, now)
                return
        if self.bottom >= ground:
            self.bottom = ground
            self._land_on_ground(screen, now)

    def _land_on_window(self, hwnd, rect, now):
        self.place = "perch"
        self.perch_hwnd = hwnd
        self.bottom = rect.top()
        self.perch_dx = self.cx - rect.left()
        self.vx = self.vy = 0.0
        self.land_t = now
        self.cat.on_landed(on_window=True)

    def _land_on_ground(self, screen, now):
        cat = self.cat
        self.vx = self.vy = 0.0
        self.land_t = now
        if screen is QGuiApplication.primaryScreen():
            a = screen.availableGeometry()
            span = max(1, a.width() - cat.cat_w)
            frac = (self.cx - cat.cat_w / 2.0 - a.x()) / float(span)
            self.place = "home"
            self.tilt = 0.0
            cat.pos_, cat.vel = 1.0, 0.0
            cat.choose_position(frac)                     # remembered as the new home
        else:                                             # another monitor: sit on its taskbar edge
            self.place = "perch"
            self.perch_hwnd = None
        cat.on_landed(on_window=False)

    def _step_perch(self, now):
        if self.perch_hwnd is None:
            return
        r = self.window_rect(self.perch_hwnd)
        cat = self.cat
        if r is None:                                     # closed, minimised or hidden: fall
            self._fall()
            return
        g, _ = self._screen_geo(r.center().x(), r.top() + 5)
        if r.top() - cat.cat_h < g.y() - 2:               # maximised or moved to the very top: no room
            self._fall()
            return
        cx = r.left() + self.perch_dx
        lo, hi = r.left() + EDGE_MARGIN, r.right() - EDGE_MARGIN
        if hi <= lo:
            self._fall()
            return
        cx = max(lo, min(hi, cx))
        self.perch_dx = cx - r.left()
        self.cx, self.bottom = cx, r.top()
        if self.ticks % 30 == 0:                          # covered by another window? then fall
            wins = self.list_windows()
            for i, (hwnd, _) in enumerate(wins):
                if hwnd == self.perch_hwnd:
                    if covered(wins, i, self.cx, self.bottom + 3):
                        self._fall()
                    break
