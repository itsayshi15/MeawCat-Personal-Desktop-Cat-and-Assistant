"""
Cat Arcade (mini_game.py) - mini games for Peeking Cat
=======================================================

How it works
------------
* Tray menu -> Play with the cat -> "Cat Arcade (mini games)".
* The cat grows BIG and a dark full-screen stage appears behind it with 8 games:
    1. Rock Paper Scissors  - best of 5, shaking fists, cat reactions
    2. Catch the Treats     - click the falling food to feed the cat (25 s)
    3. Cup Game             - follow the fish under the cups
    4. Memory Match         - find the 8 pairs in as few moves as you can
    5. Whack-a-Mouse        - bonk the mice, NOT the dog (30 s)
    6. Typing Race          - type the words faster than the cat runs
    7. Quick Maths          - answer as many sums as you can (45 s)
    8. Snake                - the cat-snake eats fish and grows
* Press 1-8 in the menu to start a game. You can also PET the cat: click on it.
* Esc = back / exit.  The X button (top right) closes the arcade.
* When you close the arcade, the cat goes back to its normal size, place and mood.

Main_file.pyw uses:  GameManager(assistant), .start_game(), .is_active()
"""

import math
import random
import sys
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QMessageBox, QWidget

try:
    from cat_features import play_cat_sound
except Exception:                  # the arcade still works without sounds
    play_cat_sound = None

# ----------------------------------------------------------------------
# SETTINGS you can change
# ----------------------------------------------------------------------
CAT_HEIGHT_FRACTION = 0.34     # big cat height = this part of the screen height
CAT_CENTER_Y = 0.46            # where the middle of the cat is (0 = top, 1 = bottom)
RPS_MAX_ROUNDS = 5             # rock paper scissors: rounds in one match
RPS_WINS_NEEDED = 3            # first to this many wins takes the match
TREAT_SECONDS = 25.0           # catch the treats: game length
CUPS_LIVES = 3                 # cup game: wrong guesses allowed
CUP = 0.13                     # cup size (part of the screen height)
WHACK_SECONDS = 30.0           # whack-a-mouse: game length
TYPE_RACE_WORDS = 12           # typing race: words in one race
TYPE_CAT_WPM = 20              # typing race: how fast the cat runs at first (words per minute)
MATH_SECONDS = 45.0            # quick maths: game length
SNAKE_START_STEP = 0.14        # snake: seconds per step at the start (smaller = faster)

if sys.platform == "win32":
    TEXT_FONT, EMOJI_FONT = "Segoe UI", "Segoe UI Emoji"
elif sys.platform == "darwin":
    TEXT_FONT, EMOJI_FONT = "Helvetica Neue", "Apple Color Emoji"
else:
    TEXT_FONT, EMOJI_FONT = "DejaVu Sans", "Noto Color Emoji"

# colours
WHITE = QColor(255, 255, 255)
CREAM = QColor(255, 240, 227)
DARK = QColor(43, 38, 34)
ORANGE = QColor(255, 154, 90)
GREEN = QColor(111, 211, 165)
RED = QColor(255, 107, 107)
YELLOW = QColor(255, 211, 107)
PINK = QColor(255, 122, 168)
GREY = QColor(190, 190, 200)

HANDS = {"rock": "\u270a", "paper": "\u270b", "scissors": "\u270c\ufe0f"}
NAMES = {"rock": "Rock", "paper": "Paper", "scissors": "Scissors"}
MOVES = ["rock", "paper", "scissors"]
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
REASON = {("rock", "scissors"): "Rock smashes Scissors",
          ("paper", "rock"): "Paper covers Rock",
          ("scissors", "paper"): "Scissors cut Paper"}

# the 8 games of the menu: button key, name, icon (the key without "g_" is the screen name)
GAMES = [("g_rps", "Rock Paper Scissors", "\u270a"), ("g_treat", "Catch the Treats", "\U0001F41F"),
         ("g_cups", "Cup Game", "\U0001F95B"), ("g_mem", "Memory Match", "\U0001F0CF"),
         ("g_whack", "Whack-a-Mouse", "\U0001F42D"), ("g_type", "Typing Race", "\u2328\ufe0f"),
         ("g_math", "Quick Maths", "\u2795"), ("g_snake", "Snake", "\U0001F40D")]
GAME_KEYS = [g[0] for g in GAMES]
MEM_EMOJI = ["\U0001F41F", "\U0001F95B", "\U0001F9F6", "\U0001F42D", "\U0001F43E", "\U0001F98B",
             "\U0001F338", "\u2B50"]
# whack-a-mouse: the number keys work like a phone/num pad (7 8 9 on top), and Q W E / A S D / Z X C
WHACK_KEY_LABELS = [7, 8, 9, 4, 5, 6, 1, 2, 3]
WHACK_KEYS = {str(k): i for i, k in enumerate(WHACK_KEY_LABELS)}
WHACK_KEYS.update({ch: i for i, ch in enumerate("qweasdzxc")})
TYPE_WORDS = ("cat fish milk paw tail purr meow nap sun moon star tree leaf rain snow cloud wind book pen desk "
              "lamp door home park road ship boat lake river sea sand rock hill bird frog duck mouse cheese "
              "apple mango lemon bread rice tea cake honey sugar salt water juice happy funny quick slow soft "
              "warm cold green blue pink gold black white smile laugh jump run swim play sing read write draw "
              "learn think dream sleep friend family school class teacher paper music phone light night "
              "morning garden window kitten pillow blanket rainbow pencil orange banana").split()


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    t = clamp(t)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_out(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def with_alpha(color, a):
    c = QColor(color)
    c.setAlpha(int(clamp(a) * 255))
    return c


def call_main(name, *args):
    """Call a function that lives in Main_file.pyw (sound, topmost), if it exists."""
    mod = sys.modules.get("__main__")
    fn = getattr(mod, name, None)
    if callable(fn):
        try:
            return fn(*args)
        except Exception:
            return None
    return None


class Btn:
    """One clickable button that the stage draws itself."""

    def __init__(self, key, label, icon="", hint="", kind="card"):
        self.key = key
        self.label = label
        self.icon = icon
        self.hint = hint
        self.kind = kind            # "card", "small" or "wide"
        self.rect = QRectF()
        self.hover = 0.0
        self.press = 0.0
        self.enabled = True
        self.visible = True


# ----------------------------------------------------------------------
# the manager (this is what Main_file.pyw talks to)
# ----------------------------------------------------------------------
class GameManager:
    def __init__(self, assistant):
        self.assistant = assistant
        self.stage = None
        self._old_mood = "auto"
        self.spot = "center"           # where the big cat sits: "center" or "left"
        self._cur = None               # where it is right now (it glides to the spot)

    @property
    def cat(self):
        return self.assistant.cat

    @property
    def bubble(self):
        return self.assistant.bubble

    def is_active(self):
        return self.stage is not None and self.stage.alive

    def start_game(self):
        """Open the Cat Arcade."""
        if self.is_active():
            self.stage.activateWindow()
            return
        cat = self.cat
        if getattr(cat, "big_mode", False):
            return
        if getattr(cat, "paused", False):
            QMessageBox.information(None, "Peeking Cat",
                                    "The cat is paused. Please resume it first.")
            return
        try:
            if self.assistant.bubble.isVisible():
                self.assistant.dismiss()
        except Exception:
            pass

        self._enter_big_cat()
        try:
            self.stage = ArcadeStage(self)
            self.stage.start()
        except Exception:
            import traceback
            call_main("log_error", "Cat Arcade could not open:\n" + traceback.format_exc())
            self.stop_game()                  # hides a half-built stage and gives the cat its size back

    def stop_game(self):
        """Close the arcade and give the cat back its normal look."""
        stage, self.stage = self.stage, None
        if stage is not None:
            stage.shutdown()
        self._leave_big_cat()

    def spot_pos(self, spot=None):
        """Top-left corner of the cat window for a spot: "center" (old games) or "left"
        (menu and the new games, which need the room on the right)."""
        cat = self.cat
        g = QGuiApplication.primaryScreen().geometry()
        w = cat.cat_w
        if (spot or self.spot) == "left":
            cx = g.x() + max(g.width() * 0.16, w / 2.0 + g.width() * 0.02)
            cy = g.y() + g.height() * 0.56
        else:
            cx = g.x() + g.width() / 2.0
            cy = g.y() + g.height() * CAT_CENTER_Y
        return cx - w / 2.0, cy - cat.pad - cat.cat_h / 2.0

    def set_spot(self, spot, instant=False):
        self.spot = spot
        if instant or self._cur is None:
            self._cur = list(self.spot_pos())
            self._center_cat()

    def glide(self, dt):
        """Called every frame by the stage: the cat slides smoothly to its spot."""
        tx, ty = self.spot_pos()
        if self._cur is None:
            self._cur = [tx, ty]
        k = min(1.0, dt * 7.0)
        self._cur[0] += (tx - self._cur[0]) * k
        self._cur[1] += (ty - self._cur[1]) * k
        self._center_cat()

    def _center_cat(self):
        """Replaces cat.reposition() while the arcade is open."""
        cat = self.cat
        if self._cur is None:
            self._cur = list(self.spot_pos())
        w = cat.cat_w
        h = cat.cat_h + cat.pad
        x, y = int(round(self._cur[0])), int(round(self._cur[1]))
        if cat.geometry().getRect() != (x, y, w, h):
            cat.setGeometry(x, y, w, h)

    def _enter_big_cat(self):
        cat = self.cat
        self._old_mood = getattr(cat, "mood", "auto")
        g = QGuiApplication.primaryScreen().geometry()
        ratio = cat.base.width() / max(1, cat.base.height())
        width = int(g.height() * CAT_HEIGHT_FRACTION * ratio)
        width = min(width, int(g.width() * 0.42))
        self.spot, self._cur = "left", None
        cat.reposition = self._center_cat          # instance override
        cat.set_big_mode(True, width)              # keeps the cat out of hiding
        self._cur = list(self.spot_pos())
        self._center_cat()
        cat.set_temp_mood("happy")

    def _leave_big_cat(self):
        cat = self.cat
        try:
            delattr(cat, "reposition")
        except Exception:
            pass
        try:
            cat.set_big_mode(False)
        except Exception:
            pass
        back = self._old_mood if self._old_mood else "auto"
        try:
            cat.set_temp_mood(back)
        except Exception:
            pass
        try:
            cat.reposition()
            cat.wake()
        except Exception:
            pass


# ----------------------------------------------------------------------
# the stage: one full-screen window that draws everything
# ----------------------------------------------------------------------
class ArcadeStage(QWidget):
    def __init__(self, manager):
        super().__init__()
        self.mgr = manager
        self.cat = manager.cat
        self.alive = True

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self.W, self.H = 1920, 1080
        self.mouse = QPointF(-1000, -1000)
        self.buttons = []
        self.B = {}
        self.particles = []
        self.floats = []
        self.flying = []
        self.rain = 0.0
        self.t_total = 0.0
        self.last_pet = 0.0
        self.mood_token = 0

        self.screen_name = "menu"
        self.msg_main = ""
        self.msg_sub = ""
        self.msg_col = WHITE
        self.msg_t = 0.0
        self.msg_y = 0.70
        self.msg_size = 1.0

        self.stars = [(random.random(), random.random(), random.random() * 6.28,
                       random.uniform(0.6, 2.2)) for _ in range(46)]

        self.stats = self._load_stats()
        self.r = {}
        self.tr = {}
        self.c = {}

        self.last = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def start(self):
        g = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(g)
        self.W, self.H = g.width(), g.height()
        self.go_menu()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        call_main("force_topmost", self.cat)        # the cat stays above the stage
        self.last = time.perf_counter()
        self.timer.start()

    def shutdown(self):
        self.alive = False
        self.timer.stop()
        self.mood_token += 1
        self.hide()
        self.deleteLater()

    def closeEvent(self, event):
        """Alt+F4 on the stage: close the arcade properly (otherwise the stage is gone but the cat
        stays huge and the arcade can never be opened again)."""
        if self.alive:
            event.ignore()
            QTimer.singleShot(0, self.mgr.stop_game)
            return
        event.accept()

    def resizeEvent(self, event):
        self.W, self.H = max(1, self.width()), max(1, self.height())
        self.layout_buttons()
        super().resizeEvent(event)

    def _load_stats(self):
        base = {"rps_w": 0, "rps_l": 0, "rps_d": 0, "treat_best": 0, "cups_best": 0,
                "mem_best": 0, "whack_best": 0, "type_best": 0, "math_best": 0, "snake_best": 0}
        saved = getattr(self.cat, "saved", None)
        if isinstance(saved, dict):
            data = saved.get("arcade")
            if not isinstance(data, dict):
                data = {}
                saved["arcade"] = data
            for k, v in base.items():
                if not isinstance(data.get(k), int):
                    data[k] = v
            return data
        return base

    def _save_stats(self):
        try:
            self.cat.save_settings()
        except Exception:
            pass

    def cat_rect(self):
        c = self.cat
        p = self.mapFromGlobal(c.pos())
        return QRectF(p.x(), p.y() + c.pad, c.cat_w, c.cat_h)

    def mood(self, key, ms=0, back="normal"):
        """Change the cat mood. After ms milliseconds go to the 'back' mood."""
        self.mood_token += 1
        token = self.mood_token
        try:
            self.cat.set_temp_mood(key)
        except Exception:
            pass
        if ms > 0:
            QTimer.singleShot(ms, lambda: self._mood_back(token, back))

    def _mood_back(self, token, back):
        if self.alive and token == self.mood_token:
            try:
                self.cat.set_temp_mood(back)
            except Exception:
                pass

    def meow(self):
        saved = getattr(self.cat, "saved", {})
        if play_cat_sound is not None and saved.get("meow", True):
            play_cat_sound("random")

    def pet_cat(self, pos):
        now = time.perf_counter()
        if now - self.last_pet < 0.5:
            return
        self.last_pet = now
        self.burst(pos.x(), pos.y(), "heart", 7)
        self.mood("love", 1500, "normal")
        if random.random() < 0.3:
            self.meow()

    def set_msg(self, main, sub="", color=None, y=0.70, size=1.0):
        self.msg_main, self.msg_sub = main, sub
        self.msg_col = color or WHITE
        self.msg_y = y
        self.msg_size = size
        self.msg_t = 0.0

    def burst(self, x, y, kind, n, colors=None):
        H = self.H
        cols = colors or [RED, ORANGE, YELLOW, GREEN, PINK, QColor(120, 180, 255)]
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(0.15, 0.55) * H
            if kind == "heart":
                ang = random.uniform(-math.pi * 0.9, -math.pi * 0.1)
                sp = random.uniform(0.08, 0.3) * H
            self.particles.append({
                "x": x, "y": y, "vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp,
                "rot": random.uniform(0, 360), "vr": random.uniform(-400, 400),
                "life": 0.0, "max": random.uniform(0.9, 1.7),
                "size": random.uniform(0.012, 0.024) * H, "color": random.choice(cols),
                "kind": kind})

    def add_float(self, x, y, text, color=WHITE, size=0.045):
        self.floats.append({"x": x, "y": y, "text": text, "color": color,
                            "t": 0.0, "life": 1.1, "size": size})

    def update_effects(self, dt):
        H = self.H
        if self.rain > 0:
            self.rain -= dt
            for _ in range(3):
                self.particles.append({
                    "x": random.uniform(0, self.W), "y": -20, "vx": random.uniform(-80, 80),
                    "vy": random.uniform(0.2, 0.45) * H, "rot": random.uniform(0, 360),
                    "vr": random.uniform(-300, 300), "life": 0.0, "max": 3.0,
                    "size": random.uniform(0.012, 0.022) * H,
                    "color": random.choice([RED, ORANGE, YELLOW, GREEN, PINK]),
                    "kind": "confetti"})
        for p in self.particles:
            p["life"] += dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vr"] * dt
            if p["kind"] == "confetti":
                p["vy"] += 0.9 * H * dt
                p["vx"] *= 0.99
            elif p["kind"] == "heart":
                p["vy"] -= 0.05 * H * dt
            else:
                p["vy"] += 0.5 * H * dt
        self.particles = [p for p in self.particles if p["life"] < p["max"]]
        for f in self.floats:
            f["t"] += dt
            f["y"] -= 0.07 * H * dt
        self.floats = [f for f in self.floats if f["t"] < f["life"]]

    def make_buttons(self, specs):
        """specs: list of Btn. Adds the two buttons that every screen has."""
        self.B = {}
        self.buttons = []
        for b in specs:
            self.B[b.key] = b
            self.buttons.append(b)
        home = Btn("home", "\U0001F3E0 Menu", kind="small")
        home.visible = self.screen_name != "menu"
        exit_ = Btn("exit", "\u2715", kind="small")
        for b in (home, exit_):
            self.B[b.key] = b
            self.buttons.append(b)
        self.layout_buttons()

    def layout_buttons(self):
        """Put every button in its place (all sizes are a part of the screen height)."""
        W, H = self.W, self.H
        B = self.B
        if "exit" in B:
            s = 0.07 * H
            B["exit"].rect = QRectF(W - s - 0.025 * H, 0.025 * H, s, s)
        if "home" in B:
            B["home"].rect = QRectF(0.025 * H, 0.025 * H, 0.17 * H, 0.07 * H)

        if self.screen_name == "menu":
            pr = self.play_rect()
            gap = 0.016 * W
            w = (pr.width() - 3 * gap) / 4.0
            h = min(0.25 * H, w * 0.95)
            for i, key in enumerate(GAME_KEYS):
                if key in B:
                    row, col = divmod(i, 4)
                    B[key].rect = QRectF(pr.left() + col * (w + gap), 0.23 * H + row * (h + 0.075 * H), w, h)
        elif self.screen_name == "math":
            pr = self.play_rect()
            w, h, gap = min(0.3 * H, pr.width() * 0.4), 0.11 * H, 0.025 * H
            for i in range(4):
                key = "ans%d" % i
                if key in B:
                    row, col = divmod(i, 2)
                    B[key].rect = QRectF(pr.center().x() - w - gap / 2 + col * (w + gap),
                                         0.5 * H + row * (h + gap), w, h)
        elif self.screen_name == "rps":
            w, h, gap = 0.21 * H, 0.2 * H, 0.03 * H
            total = 3 * w + 2 * gap
            x0 = (W - total) / 2
            for i, key in enumerate(MOVES):
                if key in B:
                    B[key].rect = QRectF(x0 + i * (w + gap), 0.775 * H, w, h)
        if "again" in B and "home2" in B:
            w, h, gap = 0.3 * H, 0.1 * H, 0.03 * H
            mid = self.play_rect().center().x() if self.mgr.spot == "left" else W / 2
            x0 = mid - (2 * w + gap) / 2
            B["again"].rect = QRectF(x0, 0.86 * H, w, h)
            B["home2"].rect = QRectF(x0 + w + gap, 0.86 * H, w, h)

    def button_at(self, pos):
        for b in reversed(self.buttons):
            if b.visible and b.enabled and b.rect.contains(pos):
                return b
        return None

    def mouseMoveEvent(self, event):
        self.mouse = QPointF(event.position())

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(event.position())
        self.mouse = pos
        b = self.button_at(pos)
        if b is not None:
            b.press = 1.0
            self.on_button(b.key)
            return
        if self.screen_click(pos):
            return
        if self.cat_rect().adjusted(-10, -10, 10, 10).contains(pos):
            self.pet_cat(pos)

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text().lower()
        if key == Qt.Key.Key_Escape:
            if self.screen_name == "menu":
                self.mgr.stop_game()
            else:
                self.go_menu()
            return
        if self.screen_name == "menu":
            if text in "12345678" and text:
                self.on_button(GAME_KEYS[int(text) - 1])
            return
        over = ("again" in self.B and self.B["again"].visible)
        if over and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.on_button("again")
            return
        if self.screen_name == "type":
            self.type_key(event.text())
            return
        if self.screen_name == "snake":
            self.snake_key(key, text)
            return
        if self.screen_name == "whack":
            if text in WHACK_KEYS:
                self.whack_hit(WHACK_KEYS[text])
            return
        if self.screen_name == "math":
            if text in ("1", "2", "3", "4"):
                self.math_pick(int(text) - 1)
            return
        if self.screen_name == "rps":
            keys = {"1": "rock", "2": "paper", "3": "scissors",
                    "r": "rock", "p": "paper", "s": "scissors"}
            if text in keys:
                self.rps_choose(keys[text])
        elif self.screen_name == "cups":
            if text in ("1", "2", "3"):
                self.cups_pick_slot(int(text) - 1)

    def on_button(self, key):
        if key == "exit":
            self.mgr.stop_game()
        elif key in ("home", "home2"):
            self.go_menu()
        elif key in GAME_KEYS:
            getattr(self, "go_" + key[2:])()
        elif key == "again":
            getattr(self, "go_" + self.screen_name, self.go_menu)()
        elif key in MOVES:
            self.rps_choose(key)
        elif key.startswith("ans"):
            self.math_pick(int(key[3:]))

    def screen_click(self, pos):
        handler = getattr(self, self.screen_name + "_click", None)
        return bool(handler(pos)) if handler else False

    def tick(self):
        if not self.alive:
            return
        now = time.perf_counter()
        dt = min(0.05, now - self.last)
        self.last = now
        self.t_total += dt
        self.msg_t += dt
        self.mouse = QPointF(self.mapFromGlobal(QCursor.pos()))

        pointer = False
        for b in self.buttons:
            over = b.visible and b.enabled and b.rect.contains(self.mouse)
            b.hover += ((1.0 if over else 0.0) - b.hover) * min(1.0, dt * 14)
            b.press = max(0.0, b.press - dt * 6)
            pointer = pointer or over
        pointer = pointer or self.wants_pointer()
        self.setCursor(Qt.CursorShape.PointingHandCursor if pointer else Qt.CursorShape.ArrowCursor)

        self.mgr.glide(dt)
        self.update_effects(dt)
        step = getattr(self, "step_" + self.screen_name, None)
        if step:
            step(dt)
        self.update()

    def wants_pointer(self):
        if self.screen_name == "cups" and self.c.get("phase") == "choose":
            return any(self.cup_rect(i).contains(self.mouse) for i in range(3))
        if self.screen_name == "treat" and self.tr.get("phase") == "play":
            return any(math.hypot(self.mouse.x() - it["x"], self.mouse.y() - it["y"])
                       < it["size"] * 0.7 for it in self.tr["items"])
        if self.screen_name == "mem" and self.m.get("phase") == "play":
            return self.mem_card_at(self.mouse) is not None
        if self.screen_name == "whack" and self.wk.get("phase") == "play":
            return self.whack_hole_at(self.mouse) is not None
        return False

    def go_menu(self):
        self.screen_name = "menu"
        self.mgr.set_spot("left")
        self.particles.clear()
        self.floats.clear()
        self.flying.clear()
        self.rain = 0.0
        self.make_buttons([Btn(key, label, icon, "Press %d" % (i + 1))
                           for i, (key, label, icon) in enumerate(GAMES)])
        self.set_msg("")
        self.mood("happy")

    def go_rps(self):
        self.screen_name = "rps"
        self.mgr.set_spot("center")
        self.particles.clear()
        self.floats.clear()
        self.rain = 0.0
        self.r = {"you": 0, "cat": 0, "rnd": 1, "phase": "pick", "t": 0.0, "beat": -1,
                  "pc": None, "cc": None, "res": None, "hist": [], "will_over": False}
        specs = [Btn(m, NAMES[m], HANDS[m], str(i + 1)) for i, m in enumerate(MOVES)]
        again = Btn("again", "\u21BB Play again", kind="wide")
        home2 = Btn("home2", "\U0001F3E0 Menu", kind="wide")
        again.visible = home2.visible = False
        self.make_buttons(specs + [again, home2])
        self.set_msg("Choose your move!")
        self.mood("normal")

    def rps_show_pick_buttons(self, on):
        for m in MOVES:
            if m in self.B:
                self.B[m].visible = on

    def rps_choose(self, move):
        r = self.r
        if self.screen_name != "rps" or r.get("phase") != "pick":
            return
        r["pc"] = move
        r["cc"] = random.choice(MOVES)
        r["phase"] = "count"
        r["t"] = 0.0
        r["beat"] = -1
        self.rps_show_pick_buttons(False)
        self.mood("normal")

    def step_rps(self, dt):
        r = self.r
        r["t"] += dt
        if r["phase"] == "count":
            beat = int(r["t"] / 0.5)
            if beat != r["beat"]:
                r["beat"] = beat
                words = ["Rock...", "Paper...", "Scissors...", "SHOOT!"]
                word = words[min(beat, 3)]
                self.set_msg(word, color=YELLOW if beat < 3 else ORANGE, y=0.72,
                             size=1.0 if beat < 3 else 1.3)
            if r["t"] >= 1.9:
                self.rps_reveal()
        elif r["phase"] == "reveal":
            if r["t"] >= 2.1:
                if r["will_over"]:
                    self.rps_finish()
                else:
                    r["rnd"] += 1
                    r["phase"] = "pick"
                    r["t"] = 0.0
                    r["pc"] = r["cc"] = r["res"] = None
                    self.rps_show_pick_buttons(True)
                    self.set_msg("Choose your move!")
                    self.mood("normal")

    def rps_reveal(self):
        r = self.r
        pc, cc = r["pc"], r["cc"]
        r["phase"] = "reveal"
        r["t"] = 0.0
        if pc == cc:
            res = "tie"
            self.set_msg("It's a tie!", "We both chose %s" % NAMES[pc], YELLOW, y=0.72)
            self.mood("confused", 2000)
        elif BEATS[pc] == cc:
            res = "win"
            r["you"] += 1
            self.set_msg("You win this round! \U0001F389", REASON[(pc, cc)], GREEN, y=0.72)
            self.mood("sad", 2000)
            self.burst(self.W / 2, self.H * 0.5, "confetti", 40)
        else:
            res = "lose"
            r["cat"] += 1
            self.set_msg("Cat wins this round! \U0001F63C", REASON[(cc, pc)], RED, y=0.72)
            self.mood("dance", 2000)
            self.meow()
        r["res"] = res
        r["hist"].append(res)
        r["will_over"] = (r["you"] >= RPS_WINS_NEEDED or r["cat"] >= RPS_WINS_NEEDED
                          or len(r["hist"]) >= RPS_MAX_ROUNDS)

    def rps_finish(self):
        r = self.r
        r["phase"] = "over"
        if r["you"] > r["cat"]:
            self.stats["rps_w"] += 1
            self.set_msg("\U0001F3C6 You beat the cat!", "Final score  %d - %d" % (r["you"], r["cat"]),
                         GREEN, y=0.70, size=1.2)
            self.mood("cry", 4000)
            self.rain = 2.5
        elif r["cat"] > r["you"]:
            self.stats["rps_l"] += 1
            self.set_msg("\U0001F63C The cat wins the match!", "Final score  %d - %d" % (r["you"], r["cat"]),
                         RED, y=0.70, size=1.2)
            self.mood("dance", 4000)
            self.meow()
        else:
            self.stats["rps_d"] += 1
            self.set_msg("\U0001F91D It's a draw!", "Final score  %d - %d" % (r["you"], r["cat"]),
                         YELLOW, y=0.70, size=1.2)
            self.mood("confused", 3000)
        self._save_stats()
        self.B["again"].visible = True
        self.B["home2"].visible = True

    def draw_rps(self, p):
        W, H = self.W, self.H
        r = self.r
        cr = self.cat_rect()
        self.pill(p, W / 2 - 0.3 * H, 0.09 * H, "YOU", str(r["you"]), GREEN)
        self.pill(p, W / 2 + 0.3 * H, 0.09 * H, "CAT", str(r["cat"]), ORANGE)
        shown = min(r["rnd"], RPS_MAX_ROUNDS)
        self.draw_text(p, "Round %d of %d" % (shown, RPS_MAX_ROUNDS), W / 2, 0.045 * H, 0.032 * H, WHITE, shadow=True)
        for i in range(RPS_MAX_ROUNDS):
            x = W / 2 + (i - (RPS_MAX_ROUNDS - 1) / 2) * 0.045 * H
            y = 0.1 * H
            rad = 0.015 * H
            if i < len(r["hist"]):
                col = {"win": GREEN, "lose": RED, "tie": GREY}[r["hist"][i]]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
            else:
                p.setPen(QPen(with_alpha(WHITE, 0.6), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), rad, rad)

        size = 0.15 * H
        yc = cr.center().y()
        lx = max(size * 0.8, cr.left() - size * 0.8)
        rx = min(W - size * 0.8, cr.right() + size * 0.8)
        t = r["t"]
        ph = r["phase"]
        if ph == "count":
            frac = (t % 0.5) / 0.5
            bob = -math.sin(math.pi * frac) * 0.07 * H if t < 1.5 else 0.0
            lh = ch = HANDS["rock"]
            sl = sc = 1.0
        elif ph in ("reveal", "over"):
            bob = 0.0
            lh, ch = HANDS[r["pc"]], HANDS[r["cc"]]
            pop = ease_out_back(min(1.0, t / 0.45)) if ph == "reveal" else 1.0
            sl = sc = 0.4 + 0.6 * pop
        else:
            bob = math.sin(self.t_total * 2.5) * 0.012 * H
            lh = ch = HANDS["rock"]
            sl = sc = 1.0
        res = r["res"] if ph in ("reveal", "over") else None
        self.draw_hand(p, lh, lx, yc + bob, size, False, GREEN if res == "win" else None, sl, 0)
        self.draw_hand(p, ch, rx, yc + bob, size, True, ORANGE if res == "lose" else None, sc, 0)
        self.draw_text(p, "YOU", lx, yc + size * 0.85, 0.028 * H, WHITE, shadow=True)
        self.draw_text(p, "CAT", rx, yc + size * 0.85, 0.028 * H, WHITE, shadow=True)

    KINDS = [("fish", "\U0001F41F", 1, 0.60), ("shrimp", "\U0001F364", 2, 0.18),
             ("chili", "\U0001F336\ufe0f", -2, 0.22)]

    def go_treat(self):
        self.screen_name = "treat"
        self.mgr.set_spot("center")
        self.particles.clear()
        self.floats.clear()
        self.flying.clear()
        self.rain = 0.0
        self.tr = {"phase": "ready", "t": 0.0, "score": 0, "left": TREAT_SECONDS, "items": [],
                   "spawn": 0.0, "combo": 0, "elapsed": 0.0, "beat": -1}
        again = Btn("again", "\u21BB Play again", kind="wide")
        home2 = Btn("home2", "\U0001F3E0 Menu", kind="wide")
        again.visible = home2.visible = False
        self.make_buttons([again, home2])
        self.set_msg("Get ready!", "Click the food to feed me \U0001F41F  -  avoid the chili \U0001F336\ufe0f",
                     YELLOW, y=0.72)
        self.mood("happy")

    def treat_lane_x(self, size):
        r = self.cat_rect()
        W = self.W
        m = size * 0.7
        lanes = [(m, r.left() - m * 1.2), (r.right() + m * 1.2, W - m)]
        lanes = [ln for ln in lanes if ln[1] - ln[0] > size]
        if not lanes:
            lanes = [(m, W - m)]
        lane = random.choices(lanes, weights=[b - a for a, b in lanes])[0]
        return random.uniform(*lane)

    def treat_spawn(self):
        tr = self.tr
        H = self.H
        kind = random.choices(self.KINDS, weights=[k[3] for k in self.KINDS])[0]
        speed = {"fish": (0.30, 0.45), "shrimp": (0.50, 0.68), "chili": (0.30, 0.45)}[kind[0]]
        boost = 1.0 + tr["elapsed"] / 60.0
        size = 0.09 * H
        tr["items"].append({"kind": kind[0], "emoji": kind[1], "pts": kind[2],
                            "x": self.treat_lane_x(size), "y": -size,
                            "vy": random.uniform(*speed) * H * boost, "size": size,
                            "ph": random.uniform(0, 6.28)})

    def step_treat(self, dt):
        tr = self.tr
        H = self.H
        tr["t"] += dt
        for f in self.flying:
            f["t"] += dt
        done = [f for f in self.flying if f["t"] >= f["dur"]]
        self.flying = [f for f in self.flying if f["t"] < f["dur"]]
        for f in done:
            self.treat_arrive(f)

        if tr["phase"] == "ready":
            beat = int(tr["t"] / 0.5)
            if beat != tr["beat"]:
                tr["beat"] = beat
                words = ["3", "2", "1", "GO!"]
                if beat < 4:
                    self.set_msg(words[beat], "Click the food to feed me, avoid the chili!",
                                 ORANGE if beat == 3 else YELLOW, y=0.72, size=1.5)
            if tr["t"] >= 2.0:
                tr["phase"] = "play"
                self.set_msg("")
        elif tr["phase"] == "play":
            tr["elapsed"] += dt
            tr["left"] -= dt
            tr["spawn"] -= dt
            if tr["spawn"] <= 0:
                self.treat_spawn()
                tr["spawn"] = max(0.28, 0.75 - tr["elapsed"] * 0.018)
            for it in tr["items"]:
                it["y"] += it["vy"] * dt
            kept = []
            for it in tr["items"]:
                if it["y"] > H + it["size"]:
                    if it["pts"] > 0:
                        tr["combo"] = 0          # a missed food breaks the combo
                else:
                    kept.append(it)
            tr["items"] = kept
            if tr["left"] <= 0:
                self.treat_finish()
        else:
            for it in tr["items"]:
                it["y"] += it["vy"] * dt
            tr["items"] = [it for it in tr["items"] if it["y"] < H + it["size"]]

    def treat_click(self, pos):
        tr = self.tr
        if tr.get("phase") != "play":
            return False
        for it in reversed(tr["items"]):
            if math.hypot(pos.x() - it["x"], pos.y() - it["y"]) <= it["size"] * 0.7:
                tr["items"].remove(it)
                self.treat_collect(it)
                return True
        return False

    def treat_collect(self, it):
        tr = self.tr
        cr = self.cat_rect()
        target = (cr.center().x(), cr.top() + cr.height() * 0.55)
        self.flying.append({"emoji": it["emoji"], "x0": it["x"], "y0": it["y"],
                            "x1": target[0], "y1": target[1], "t": 0.0, "dur": 0.35,
                            "size": it["size"], "kind": it["kind"]})
        if it["pts"] > 0:
            tr["combo"] += 1
            gain = it["pts"]
            self.add_float(it["x"], it["y"], "+%d" % gain, GREEN)
            if tr["combo"] % 5 == 0:
                gain += 3
                self.add_float(it["x"], it["y"] - 0.05 * self.H, "COMBO +3!", YELLOW, 0.05)
            tr["score"] += gain
        else:
            tr["combo"] = 0
            tr["score"] = max(0, tr["score"] + it["pts"])
            self.add_float(it["x"], it["y"], "%d" % it["pts"], RED)

    def treat_arrive(self, f):
        cr = self.cat_rect()
        if f["kind"] == "chili":
            self.burst(f["x1"], f["y1"], "spark", 14, [RED, ORANGE, YELLOW])
            self.mood("angry", 1300, "happy")
        else:
            self.burst(f["x1"], f["y1"], "spark", 8, [YELLOW, WHITE, PINK])
            if self.tr.get("combo", 0) and self.tr["combo"] % 5 == 0:
                self.mood("dance", 1600, "happy")
                self.burst(cr.center().x(), cr.top(), "heart", 8)
            else:
                self.mood("happy", 700, "happy")

    def treat_finish(self):
        tr = self.tr
        tr["phase"] = "over"
        score = tr["score"]
        best = self.stats["treat_best"]
        new_best = score > best
        if new_best:
            self.stats["treat_best"] = score
        self._save_stats()
        if score >= 30:
            praise = "Fish master! \U0001F451"
        elif score >= 18:
            praise = "Great job! \U0001F60A"
        elif score >= 8:
            praise = "Not bad! \U0001F44D"
        else:
            praise = "I'm still hungry... \U0001F63F"
        self.set_msg("Time's up!  Score: %d" % score,
                     ("\U0001F31F New best!  " if new_best else "Best: %d   " % self.stats["treat_best"]) + praise,
                     YELLOW, y=0.70, size=1.2)
        self.mood("love" if score >= 8 else "sad", 3500, "normal")
        if score >= 8:
            self.rain = 2.0
            self.meow()
        self.B["again"].visible = True
        self.B["home2"].visible = True

    def draw_treat(self, p):
        W, H = self.W, self.H
        tr = self.tr
        for it in tr["items"]:
            sway = math.sin(self.t_total * 3 + it["ph"])
            x, y = it["x"] + sway * 0.01 * H, it["y"]
            halo = RED if it["kind"] == "chili" else WHITE
            rg = QRadialGradient(QPointF(x, y), it["size"] * 0.9)
            rg.setColorAt(0, with_alpha(halo, 0.45))
            rg.setColorAt(1, with_alpha(halo, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rg)
            p.drawEllipse(QPointF(x, y), it["size"] * 0.9, it["size"] * 0.9)
            self.draw_text(p, it["emoji"], x, y, it["size"], WHITE, emoji=True, angle=sway * 18)
        for f in self.flying:
            e = ease_out_cubic(f["t"] / f["dur"])
            x, y = lerp(f["x0"], f["x1"], e), lerp(f["y0"], f["y1"], e)
            self.draw_text(p, f["emoji"], x, y, f["size"] * (1.0 - 0.6 * e), WHITE, emoji=True)
        self.pill(p, W / 2 - 0.2 * H, 0.09 * H, "SCORE", str(tr["score"]), GREEN)
        left = max(0.0, tr["left"]) if tr["phase"] != "ready" else TREAT_SECONDS
        low = left <= 5 and tr["phase"] == "play"
        self.pill(p, W / 2 + 0.2 * H, 0.09 * H, "TIME", "%d" % math.ceil(left), RED if low else ORANGE)
        if tr["combo"] >= 2 and tr["phase"] == "play":
            self.draw_text(p, "Combo x%d" % tr["combo"], W / 2, 0.17 * H, 0.032 * H, YELLOW, shadow=True)
        if tr["phase"] == "play":
            self.draw_text(p, "Click the food!  Avoid \U0001F336\ufe0f", W / 2, 0.965 * H, 0.026 * H,
                           with_alpha(WHITE, 0.75), bold=False, shadow=True)

    def go_cups(self):
        self.screen_name = "cups"
        self.mgr.set_spot("center")
        self.particles.clear()
        self.floats.clear()
        self.flying.clear()
        self.rain = 0.0
        self.c = {"phase": "intro", "t": 0.0, "level": 1, "lives": CUPS_LIVES, "score": 0,
                  "cups": [], "swaps": [], "swap_i": 0, "swap_t": 0.0, "swap_dur": 0.4,
                  "pick": None, "judged": False, "correct": False}
        again = Btn("again", "\u21BB Play again", kind="wide")
        home2 = Btn("home2", "\U0001F3E0 Menu", kind="wide")
        again.visible = home2.visible = False
        self.make_buttons([again, home2])
        self.cups_begin_round()

    def cups_begin_round(self):
        c = self.c
        fish = random.randint(0, 2)
        c["cups"] = [{"x": float(i - 1), "slot": i, "fish": i == fish, "lift": 0.0, "yoff": 0.0}
                     for i in range(3)]
        c["phase"] = "intro"
        c["t"] = 0.0
        c["pick"] = None
        c["judged"] = False
        self.set_msg("Level %d  -  Watch the fish! \U0001F41F" % c["level"], y=0.69, size=0.8)
        self.mood("happy")

    def cups_make_swaps(self):
        c = self.c
        n = min(14, 4 + 2 * (c["level"] - 1))
        swaps = []
        last = None
        for _ in range(n):
            while True:
                pair = tuple(sorted(random.sample(range(3), 2)))     # slots
                if pair != last:
                    break
            swaps.append(pair)
            last = pair
        c["swaps"] = swaps
        c["swap_i"] = 0
        c["swap_t"] = 0.0
        c["swap_dur"] = max(0.15, 0.42 - 0.035 * (c["level"] - 1))

    def cup_in_slot(self, slot):
        for cup in self.c["cups"]:
            if cup["slot"] == slot:
                return cup
        return None

    def step_cups(self, dt):
        c = self.c
        c["t"] += dt
        ph = c["phase"]
        cups = c["cups"]
        targets = {id(cup): 0.0 for cup in cups}
        if ph == "intro":
            if 0.3 < c["t"] < 1.8:
                for cup in cups:
                    if cup["fish"]:
                        targets[id(cup)] = 1.0
            if c["t"] >= 2.3:
                c["phase"] = "shuffle"
                self.cups_make_swaps()
                self.set_msg("Follow the fish! \U0001F440", y=0.69, size=0.8)
        elif ph == "shuffle":
            i = c["swap_i"]
            if i < len(c["swaps"]):
                sa, sb = c["swaps"][i]
                a, b = self.cup_in_slot(sa), self.cup_in_slot(sb)
                c["swap_t"] += dt / c["swap_dur"]
                e = ease_in_out(c["swap_t"])
                a["x"] = lerp(sa - 1, sb - 1, e)
                b["x"] = lerp(sb - 1, sa - 1, e)
                a["yoff"] = -math.sin(math.pi * clamp(c["swap_t"])) * 0.05
                b["yoff"] = math.sin(math.pi * clamp(c["swap_t"])) * 0.05
                if c["swap_t"] >= 1.0:
                    a["x"], b["x"] = float(sb - 1), float(sa - 1)
                    a["slot"], b["slot"] = sb, sa
                    a["yoff"] = b["yoff"] = 0.0
                    c["swap_i"] += 1
                    c["swap_t"] = 0.0
            else:
                c["phase"] = "choose"
                c["t"] = 0.0
                self.set_msg("Where is the fish? Click a cup!", "or press 1, 2, 3", y=0.69, size=0.8)
        elif ph == "choose":
            for cup in cups:
                if self.cup_rect(self.cup_index_slot(cup)).contains(self.mouse):
                    targets[id(cup)] = 0.1
        elif ph == "reveal":
            pick = c["pick"]
            if c["t"] > 0.1 and not c["judged"]:
                self.cups_judge()
            targets[id(pick)] = 1.0
            if c["t"] > 0.7:
                for cup in cups:
                    if cup["fish"]:
                        targets[id(cup)] = 1.0
            if c["t"] >= 2.3:
                if c["lives"] <= 0:
                    self.cups_finish()
                else:
                    c["level"] += 1
                    self.cups_begin_round()
        for cup in cups:
            cup["lift"] += (targets.get(id(cup), 0.0) - cup["lift"]) * min(1.0, dt * 12)

    def cup_index_slot(self, cup):
        return cup["slot"]

    def cup_geom(self, x_units):
        H, W = self.H, self.W
        spacing = 0.27 * H
        return W / 2 + x_units * spacing, 0.965 * H

    def cup_rect(self, slot):
        cup = self.cup_in_slot(slot) if self.c.get("cups") else None
        if cup is None:
            return QRectF()
        cx, base = self.cup_geom(cup["x"])
        w, h = CUP * self.H, CUP * self.H
        return QRectF(cx - w / 2, base - h - 0.02 * self.H, w, h + 0.03 * self.H)

    def cups_click(self, pos):
        if self.c.get("phase") != "choose":
            return False
        for slot in range(3):
            if self.cup_rect(slot).contains(pos):
                self.cups_pick_slot(slot)
                return True
        return False

    def cups_pick_slot(self, slot):
        c = self.c
        if self.screen_name != "cups" or c.get("phase") != "choose":
            return
        c["pick"] = self.cup_in_slot(slot)
        c["phase"] = "reveal"
        c["t"] = 0.0
        c["judged"] = False

    def cups_judge(self):
        c = self.c
        c["judged"] = True
        cr = self.cat_rect()
        if c["pick"]["fish"]:
            c["correct"] = True
            c["score"] += 1
            self.set_msg("You found it! \U0001F389", y=0.69, color=GREEN, size=0.9)
            self.mood("sad", 2000)
            self.burst(self.W / 2, cr.center().y(), "confetti", 40)
        else:
            c["correct"] = False
            c["lives"] -= 1
            self.set_msg("Oops! Not there \U0001F639", y=0.69, color=RED, size=0.9)
            self.mood("dance", 2000)
            self.meow()

    def cups_finish(self):
        c = self.c
        c["phase"] = "over"
        score = c["score"]
        new_best = score > self.stats["cups_best"]
        if new_best:
            self.stats["cups_best"] = score
        self._save_stats()
        self.set_msg("Game over!  Score: %d" % score,
                     "\U0001F31F New best!" if new_best else "Best: %d" % self.stats["cups_best"],
                     YELLOW, y=0.70, size=1.0)
        self.mood("love" if score >= 3 else "normal", 3000, "normal")
        if score >= 3:
            self.rain = 1.5
        self.B["again"].visible = True
        self.B["home2"].visible = True

    def draw_cups(self, p):
        W, H = self.W, self.H
        c = self.c
        self.pill(p, W / 2 - 0.3 * H, 0.09 * H, "LEVEL", str(c["level"]), ORANGE)
        self.pill(p, W / 2, 0.09 * H, "SCORE", str(c["score"]), GREEN)
        hearts = "\u2764\ufe0f" * c["lives"] + "\U0001F5A4" * (CUPS_LIVES - c["lives"])
        self.pill(p, W / 2 + 0.3 * H, 0.09 * H, "LIVES", hearts, RED, emoji_value=True)
        if c["phase"] == "over":
            return
        if c["phase"] == "choose":
            for slot in range(3):
                rect = self.cup_rect(slot)
                if rect.contains(self.mouse):
                    rg = QRadialGradient(rect.center(), rect.width())
                    rg.setColorAt(0, with_alpha(YELLOW, 0.35))
                    rg.setColorAt(1, with_alpha(YELLOW, 0.0))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(rg)
                    p.drawEllipse(rect.center(), rect.width(), rect.width())
        for cup in c["cups"]:
            cx, base = self.cup_geom(cup["x"])
            base += cup["yoff"] * H
            w, h = CUP * H, CUP * H
            lift = cup["lift"] * 0.07 * H
            if cup["fish"] and cup["lift"] > 0.55:
                p.save()
                p.setOpacity(clamp((cup["lift"] - 0.55) / 0.3))
                self.draw_text(p, "\U0001F41F", cx, base - 0.03 * H, 0.075 * H, WHITE, emoji=True)
                p.restore()
            self.draw_cup(p, cx, base - lift, w, h)

    def draw_cup(self, p, cx, base, w, h):
        tw = w * 0.72
        path = QPainterPath()
        path.moveTo(cx - tw / 2, base - h)
        path.lineTo(cx + tw / 2, base - h)
        path.lineTo(cx + w / 2, base)
        path.lineTo(cx - w / 2, base)
        path.closeSubpath()
        grad = QLinearGradient(cx - w / 2, 0, cx + w / 2, 0)
        grad.setColorAt(0, QColor(255, 128, 92))
        grad.setColorAt(0.45, QColor(255, 176, 120))
        grad.setColorAt(1, QColor(226, 98, 72))
        p.setPen(QPen(QColor(150, 60, 40), max(2, h * 0.025)))
        p.setBrush(grad)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(WHITE, 0.55))
        sy = base - h * 0.55
        p.drawRect(QRectF(cx - lerp(tw, w, 0.45) / 2, sy, lerp(tw, w, 0.45), h * 0.1))
        p.setBrush(QColor(255, 205, 160))
        p.setPen(QPen(QColor(150, 60, 40), max(2, h * 0.02)))
        p.drawEllipse(QPointF(cx, base - h), tw / 2, h * 0.07)
        self.draw_text(p, "\U0001F43E", cx, base - h * 0.28, h * 0.3, WHITE, emoji=True)

    # ==================================================================
    # the new games: the cat sits on the left, the game is on the right
    # ==================================================================
    def play_rect(self):
        """The free area to the right of the cat (stage coordinates)."""
        W, H = self.W, self.H
        x0, _ = self.mgr.spot_pos("left")
        left = (x0 - self.x()) + self.cat.cat_w + 0.025 * W
        left = min(left, 0.45 * W)
        return QRectF(left, 0.17 * H, W - left - 0.03 * W, 0.79 * H)

    def _game_start(self, name):
        self.screen_name = name
        self.mgr.set_spot("left")
        self.particles.clear()
        self.floats.clear()
        self.flying.clear()
        self.rain = 0.0

    def _over_buttons(self, extra=()):
        again = Btn("again", "\u21bb Play again", kind="wide")
        home2 = Btn("home2", "\U0001F3E0 Menu", kind="wide")
        again.visible = home2.visible = False
        self.make_buttons(list(extra) + [again, home2])

    def _show_over_buttons(self):
        self.B["again"].visible = True
        self.B["home2"].visible = True

    def _new_best(self, key, value, lower_is_better=False):
        old = self.stats.get(key, 0)
        better = value > 0 and (old == 0 or (value < old if lower_is_better else value > old))
        if better:
            self.stats[key] = value
        self._save_stats()
        return better

    def _countdown(self, st, dt, help_text):
        """3, 2, 1, GO! Returns True when it is over."""
        st["t"] += dt
        beat = int(st["t"] / 0.5)
        if beat != st.get("beat", -1) and beat < 4:
            st["beat"] = beat
            self.set_msg(["3", "2", "1", "GO!"][beat], help_text,
                         ORANGE if beat == 3 else YELLOW, y=0.5, size=1.5)
        if st["t"] >= 2.0:
            self.set_msg("")
            return True
        return False

    def _pills(self, p, items):
        """Score pills in a row above the game."""
        H = self.H
        mid = self.play_rect().center().x()
        n = len(items)
        for i, (label, value, color) in enumerate(items):
            self.pill(p, mid + (i - (n - 1) / 2.0) * 0.27 * H, 0.09 * H, label, value, color,
                      emoji_value=label == "LIVES")

    def _help(self, p, text):
        pr = self.play_rect()
        self.draw_text(p, text, pr.center().x(), 0.965 * self.H, 0.024 * self.H,
                       with_alpha(WHITE, 0.7), bold=False, shadow=True)

    # ------------------------------------------------------------------
    # 4. MEMORY MATCH
    # ------------------------------------------------------------------
    def go_mem(self):
        self._game_start("mem")
        faces = MEM_EMOJI * 2
        random.shuffle(faces)
        self.m = {"phase": "peek", "t": 0.0, "cards": [{"e": f, "state": "up", "flip": 1.0, "shake": 0.0}
                                                      for f in faces],
                  "open": [], "hide_at": None, "moves": 0, "pairs": 0, "time": 0.0}
        self._over_buttons()
        self.set_msg("Remember the cards!", "They turn over in 2 seconds", YELLOW, y=0.12, size=0.8)
        self.mood("happy")

    def mem_geom(self):
        pr = self.play_rect()
        cell = min(pr.width() / 4.0, (pr.height() - 0.1 * self.H) / 4.0)
        x0 = pr.center().x() - 2 * cell
        y0 = pr.top() + 0.02 * self.H
        return x0, y0, cell

    def mem_rect(self, i):
        x0, y0, cell = self.mem_geom()
        row, col = divmod(i, 4)
        pad = cell * 0.07
        return QRectF(x0 + col * cell + pad, y0 + row * cell + pad, cell - 2 * pad, cell - 2 * pad)

    def mem_card_at(self, pos):
        for i, c in enumerate(self.m.get("cards", [])):
            if c["state"] == "down" and self.mem_rect(i).contains(pos):
                return i
        return None

    def step_mem(self, dt):
        m = self.m
        m["t"] += dt
        if m["phase"] == "peek" and m["t"] >= 2.2:
            for c in m["cards"]:
                c["state"] = "down"
            m["phase"] = "play"
            self.set_msg("")
        elif m["phase"] == "play":
            m["time"] += dt
            if m["hide_at"] is not None and m["t"] >= m["hide_at"]:
                for i in m["open"]:
                    m["cards"][i]["state"] = "down"
                m["open"] = []
                m["hide_at"] = None
        for c in m["cards"]:
            target = 0.0 if c["state"] == "down" else 1.0
            c["flip"] += (target - c["flip"]) * min(1.0, dt * 11.0)
            c["shake"] = max(0.0, c["shake"] - dt)

    def mem_click(self, pos):
        m = self.m
        if m["phase"] != "play" or m["hide_at"] is not None:
            return False
        i = self.mem_card_at(pos)
        if i is None:
            return False
        m["cards"][i]["state"] = "up"
        m["open"].append(i)
        if len(m["open"]) == 2:
            m["moves"] += 1
            a, b = m["open"]
            if m["cards"][a]["e"] == m["cards"][b]["e"]:
                for k in (a, b):
                    m["cards"][k]["state"] = "done"
                    r = self.mem_rect(k)
                    self.burst(r.center().x(), r.center().y(), "spark", 8, [YELLOW, WHITE, GREEN])
                m["open"] = []
                m["pairs"] += 1
                self.mood("happy", 900, "normal")
                if m["pairs"] == len(MEM_EMOJI):
                    self.mem_finish()
            else:
                m["hide_at"] = m["t"] + 0.9
                for k in (a, b):
                    m["cards"][k]["shake"] = 0.4
                self.mood("confused", 900, "normal")
        return True

    def mem_finish(self):
        m = self.m
        m["phase"] = "over"
        new_best = self._new_best("mem_best", m["moves"], lower_is_better=True)
        self.set_msg("All pairs found! \U0001F389", "%d moves  -  %d seconds  -  %s" % (
            m["moves"], m["time"], "\U0001F31F New best!" if new_best else "Best: %d moves" % self.stats["mem_best"]),
            GREEN, y=0.45, size=1.1)
        self.mood("love", 3500, "normal")
        self.rain = 2.0
        self.meow()
        self._show_over_buttons()

    def draw_mem(self, p):
        m = self.m
        self._pills(p, [("MOVES", str(m["moves"]), ORANGE), ("PAIRS", "%d/%d" % (m["pairs"], len(MEM_EMOJI)), GREEN),
                        ("TIME", "%d" % m["time"], YELLOW)])
        if m["phase"] == "over":
            return
        for i, c in enumerate(m["cards"]):
            r = self.mem_rect(i)
            f = c["flip"]
            face = f > 0.5
            sx = max(0.04, abs(2.0 * f - 1.0))
            shake = math.sin(self.t_total * 60) * c["shake"] * r.width() * 0.08
            hover = (not face and m["phase"] == "play" and r.contains(self.mouse))
            p.save()
            p.translate(r.center().x() + shake, r.center().y() - (r.height() * 0.03 if hover else 0))
            p.scale(sx, 1.0)
            rr = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
            rad = r.width() * 0.14
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 70))
            p.drawRoundedRect(rr.translated(0, r.height() * 0.04), rad, rad)
            if face:
                done = c["state"] == "done"
                p.setPen(QPen(GREEN if done else QColor(236, 198, 166), 4 if done else 3))
                p.setBrush(QColor(236, 255, 240) if done else CREAM)
                p.drawRoundedRect(rr, rad, rad)
                self.draw_text(p, c["e"], 0, 0, r.height() * 0.55, WHITE, emoji=True)
            else:
                g = QLinearGradient(rr.topLeft(), rr.bottomRight())
                g.setColorAt(0, QColor(255, 176, 120).lighter(112 if hover else 100))
                g.setColorAt(1, QColor(240, 112, 84).lighter(112 if hover else 100))
                p.setPen(QPen(QColor(255, 235, 215), 3))
                p.setBrush(g)
                p.drawRoundedRect(rr, rad, rad)
                self.draw_text(p, "\U0001F43E", 0, 0, r.height() * 0.38, WHITE, emoji=True)
            p.restore()
        self._help(p, "Click two cards. Same picture = they stay open.")

    # ------------------------------------------------------------------
    # 5. WHACK-A-MOUSE
    # ------------------------------------------------------------------
    WHACK_KINDS = [("mouse", "\U0001F42D", 1, 0.78), ("gold", "\U0001F439", 3, 0.08),
                   ("dog", "\U0001F436", -2, 0.14)]

    def go_whack(self):
        self._game_start("whack")
        self.wk = {"phase": "ready", "t": 0.0, "beat": -1, "left": WHACK_SECONDS, "score": 0,
                   "spawn": 0.4, "elapsed": 0.0, "combo": 0,
                   "holes": [{"kind": None, "e": "", "pts": 0, "up": 0.0, "stay": 0.0, "bonk": 0.0}
                             for _ in range(9)]}
        self._over_buttons()
        self.mood("happy")

    def whack_geom(self, i):
        pr = self.play_rect()
        cell = min(pr.width() / 3.0, (pr.height() - 0.08 * self.H) / 3.0)
        row, col = divmod(i, 3)
        cx = pr.center().x() + (col - 1) * cell
        cy = pr.top() + cell * (row + 0.72)
        return cx, cy, cell

    def whack_hole_at(self, pos):
        for i in range(9):
            cx, cy, cell = self.whack_geom(i)
            if abs(pos.x() - cx) < cell * 0.38 and cy - cell * 0.55 < pos.y() < cy + cell * 0.15:
                return i
        return None

    def step_whack(self, dt):
        wk = self.wk
        if wk["phase"] == "ready":
            if self._countdown(wk, dt, "Bonk the mice!  Do NOT bonk the dog \U0001F436"):
                wk["phase"] = "play"
        elif wk["phase"] == "play":
            wk["elapsed"] += dt
            wk["left"] -= dt
            wk["spawn"] -= dt
            if wk["spawn"] <= 0:
                free = [i for i, h in enumerate(wk["holes"]) if h["kind"] is None and h["up"] < 0.1]
                if free:
                    h = wk["holes"][random.choice(free)]
                    kind = random.choices(self.WHACK_KINDS, weights=[k[3] for k in self.WHACK_KINDS])[0]
                    h["kind"], h["e"], h["pts"] = kind[0], kind[1], kind[2]
                    h["stay"] = max(0.55, 1.2 - wk["elapsed"] * 0.02)
                wk["spawn"] = max(0.3, 0.85 - wk["elapsed"] * 0.016) * random.uniform(0.7, 1.2)
            if wk["left"] <= 0:
                self.whack_finish()
        for h in wk["holes"]:
            if h["kind"] is not None and wk["phase"] == "play":
                h["stay"] -= dt
                if h["stay"] <= 0:
                    if h["pts"] > 0:
                        wk["combo"] = 0
                    h["kind"] = None
            h["bonk"] = max(0.0, h["bonk"] - dt)
            target = 1.0 if h["kind"] is not None else 0.0
            h["up"] += (target - h["up"]) * min(1.0, dt * 14.0)

    def whack_click(self, pos):
        if self.wk.get("phase") != "play":
            return False
        i = self.whack_hole_at(pos)
        if i is None:
            return False
        self.whack_hit(i)
        return True

    def whack_hit(self, i):
        wk = self.wk
        if wk.get("phase") != "play":
            return
        h = wk["holes"][i]
        if h["kind"] is None or h["up"] < 0.35:
            return
        cx, cy, cell = self.whack_geom(i)
        y = cy - cell * 0.3
        h["bonk"] = 0.3
        if h["pts"] > 0:
            wk["combo"] += 1
            gain = h["pts"] + (2 if wk["combo"] % 5 == 0 else 0)
            wk["score"] += gain
            self.add_float(cx, y, "+%d" % gain, YELLOW if h["kind"] == "gold" else GREEN)
            self.burst(cx, y, "spark", 10, [YELLOW, WHITE, ORANGE])
            self.mood("happy", 600, "normal")
        else:
            wk["combo"] = 0
            wk["score"] = max(0, wk["score"] + h["pts"])
            self.add_float(cx, y, "%d  Not the dog!" % h["pts"], RED)
            self.mood("angry", 1100, "normal")
        h["kind"] = None

    def whack_finish(self):
        wk = self.wk
        wk["phase"] = "over"
        new_best = self._new_best("whack_best", wk["score"])
        self.set_msg("Time's up!  Score: %d" % wk["score"],
                     "\U0001F31F New best!" if new_best else "Best: %d" % self.stats["whack_best"],
                     YELLOW, y=0.45, size=1.2)
        self.mood("love" if wk["score"] >= 15 else "normal", 3000, "normal")
        if wk["score"] >= 15:
            self.rain = 2.0
            self.meow()
        self._show_over_buttons()

    def draw_whack(self, p):
        wk = self.wk
        low = wk["phase"] == "play" and wk["left"] <= 5
        left = WHACK_SECONDS if wk["phase"] == "ready" else max(0.0, wk["left"])
        self._pills(p, [("SCORE", str(wk["score"]), GREEN), ("TIME", "%d" % math.ceil(left), RED if low else ORANGE)])
        if wk["phase"] == "over":
            return
        for i, h in enumerate(wk["holes"]):
            cx, cy, cell = self.whack_geom(i)
            rx, ry = cell * 0.36, cell * 0.12
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(110, 74, 50))
            p.drawEllipse(QPointF(cx, cy), rx * 1.12, ry * 1.4)          # dirt mound
            p.setBrush(QColor(40, 24, 18))
            p.drawEllipse(QPointF(cx, cy), rx, ry)                       # the hole
            if h["up"] > 0.02 and h["e"]:
                p.save()
                p.setClipRect(QRectF(cx - cell, cy - cell * 1.2, cell * 2, cell * 1.2 + ry * 0.2))
                y = cy + cell * 0.25 - h["up"] * cell * 0.5
                self.draw_text(p, h["e"], cx, y, cell * 0.42, WHITE, emoji=True)
                p.restore()
            p.setPen(QPen(QColor(140, 96, 64), max(3.0, cell * 0.03)))       # front lip of the hole
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry), 180 * 16, 180 * 16)
            if h["bonk"] > 0:
                p.save()
                p.setOpacity(clamp(h["bonk"] / 0.3))
                self.draw_text(p, "\U0001F4A5", cx, cy - cell * 0.32, cell * 0.36, WHITE, emoji=True)
                p.restore()
            self.draw_text(p, str(WHACK_KEY_LABELS[i]), cx, cy + ry * 2.2, cell * 0.08, with_alpha(WHITE, 0.45))
        self._help(p, "Click the mice (or press the number keys).  Golden hamster = +3.  Dog = -2!")

    # ------------------------------------------------------------------
    # 6. TYPING RACE
    # ------------------------------------------------------------------
    def go_type(self):
        self._game_start("type")
        level = getattr(self, "_type_level", 0)
        wpm = TYPE_CAT_WPM + 4 * level
        words = random.sample(TYPE_WORDS, TYPE_RACE_WORDS)
        chars = sum(len(w) for w in words)
        self.ty = {"phase": "ready", "t": 0.0, "beat": -1, "words": words, "wi": 0, "ci": 0, "done": 0,
                   "total": chars, "elapsed": 0.0, "cat_time": chars / (wpm * 5.0 / 60.0),
                   "mistakes": 0, "correct": 0, "shake": 0.0, "wpm": wpm}
        self._over_buttons()
        self.mood("happy")

    def step_type(self, dt):
        ty = self.ty
        ty["shake"] = max(0.0, ty["shake"] - dt)
        if ty["phase"] == "ready":
            if self._countdown(ty, dt, "Type the words. The cat runs at %d words a minute!" % ty["wpm"]):
                ty["phase"] = "play"
        elif ty["phase"] == "play":
            ty["elapsed"] += dt
            if ty["elapsed"] >= ty["cat_time"]:
                self.type_finish(won=False)

    def type_key(self, text):
        ty = self.ty
        if ty.get("phase") != "play" or not text or len(text) != 1 or not text.isprintable() or text == " ":
            return
        word = ty["words"][ty["wi"]]
        if text.lower() == word[ty["ci"]].lower():
            ty["ci"] += 1
            ty["done"] += 1
            ty["correct"] += 1
            if ty["ci"] >= len(word):
                ty["wi"] += 1
                ty["ci"] = 0
                pr = self.play_rect()
                self.add_float(pr.center().x(), 0.47 * self.H, "\u2713", GREEN, 0.05)
                if ty["wi"] >= len(ty["words"]):
                    self.type_finish(won=True)
        else:
            ty["mistakes"] += 1
            ty["shake"] = 0.25

    def type_finish(self, won):
        ty = self.ty
        ty["phase"] = "over"
        minutes = max(1e-6, ty["elapsed"] / 60.0)
        wpm = int(round(ty["correct"] / 5.0 / minutes))
        acc = int(round(100.0 * ty["correct"] / max(1, ty["correct"] + ty["mistakes"])))
        new_best = self._new_best("type_best", wpm)
        info = "%d WPM  -  %d%% correct%s" % (wpm, acc, "  -  \U0001F31F New best!" if new_best else "")
        if won:
            self._type_level = getattr(self, "_type_level", 0) + 1
            self.set_msg("\U0001F3C6 You beat the cat!", info + "  -  next race the cat runs faster",
                         GREEN, y=0.45, size=1.2)
            self.mood("cry", 3500, "normal")
            self.rain = 2.5
        else:
            self.set_msg("\U0001F63C The cat wins the race!", info, RED, y=0.45, size=1.2)
            self.mood("dance", 3500, "normal")
            self.meow()
        self._show_over_buttons()

    def draw_type(self, p):
        ty = self.ty
        H = self.H
        pr = self.play_rect()
        self._pills(p, [("WORDS", "%d/%d" % (ty["wi"], len(ty["words"])), GREEN),
                        ("CAT", "%d WPM" % ty["wpm"], ORANGE)])
        if ty["phase"] == "over":
            return
        x0, x1 = pr.left() + 0.03 * H, pr.right() - 0.06 * H
        cat_prog = min(1.0, ty["elapsed"] / ty["cat_time"]) if ty["phase"] == "play" else 0.0
        you_prog = ty["done"] / float(max(1, ty["total"]))
        for k, (label, emoji, prog, color) in enumerate((("CAT", "\U0001F408", cat_prog, ORANGE),
                                                        ("YOU", "\U0001F3C3", you_prog, GREEN))):
            y = pr.top() + 0.06 * H + k * 0.13 * H
            p.setPen(QPen(with_alpha(WHITE, 0.25), 2, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x0, y + 0.04 * H), QPointF(x1, y + 0.04 * H))
            self.draw_text(p, "\U0001F3C1", x1 + 0.025 * H, y, 0.05 * H, WHITE, emoji=True)
            self.draw_text(p, label, x0 - 0.0 * H, y - 0.055 * H, 0.022 * H, color)
            bob = -abs(math.sin(self.t_total * 12)) * 0.01 * H if ty["phase"] == "play" else 0.0
            self.draw_hand(p, emoji, x0 + (x1 - x0) * prog, y + bob, 0.065 * H, True, None, 1.0, 0)
        word = ty["words"][ty["wi"]] if ty["wi"] < len(ty["words"]) else ""
        done, rest = word[:ty["ci"]], word[ty["ci"]:]
        font = self.text_font(0.1 * H)
        fm = QFontMetricsF(font)
        w_done, w_rest = fm.horizontalAdvance(done), fm.horizontalAdvance(rest)
        cx = pr.center().x() + math.sin(self.t_total * 70) * ty["shake"] * 0.06 * H
        y = 0.55 * H
        left = cx - (w_done + w_rest) / 2
        p.setFont(font)
        box = QRectF(left - 0.03 * H, y - 0.08 * H, w_done + w_rest + 0.06 * H, 0.16 * H)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 14, 34, 190) if ty["shake"] <= 0 else QColor(90, 20, 30, 200))
        p.drawRoundedRect(box, 0.03 * H, 0.03 * H)
        p.setPen(GREEN)
        p.drawText(QRectF(left, y - 0.08 * H, w_done + 2, 0.16 * H), Qt.AlignmentFlag.AlignVCenter, done)
        p.setPen(WHITE)
        p.drawText(QRectF(left + w_done, y - 0.08 * H, w_rest + 2, 0.16 * H), Qt.AlignmentFlag.AlignVCenter, rest)
        if rest:
            first = fm.horizontalAdvance(rest[0])
            p.setPen(QPen(YELLOW, max(3.0, 0.006 * H)))
            p.drawLine(QPointF(left + w_done, y + 0.055 * H), QPointF(left + w_done + first, y + 0.055 * H))
        nxt = "   ".join(ty["words"][ty["wi"] + 1:ty["wi"] + 4])
        self.draw_text(p, nxt, pr.center().x(), 0.7 * H, 0.035 * H, with_alpha(WHITE, 0.45), bold=False)
        self._help(p, "Just type the letters (no Space needed). Wrong letters shake.")

    # ------------------------------------------------------------------
    # 7. QUICK MATHS
    # ------------------------------------------------------------------
    def go_math(self):
        self._game_start("math")
        self.mt = {"phase": "ready", "t": 0.0, "beat": -1, "left": MATH_SECONDS, "score": 0, "streak": 0,
                   "q": "", "ans": 0, "opts": [], "lock": 0.0, "res": None, "pick": None}
        btns = [Btn("ans%d" % i, "", kind="wide") for i in range(4)]
        for b in btns:
            b.visible = False
        self._over_buttons(btns)
        self.mood("happy")

    def math_new(self):
        mt = self.mt
        level = mt["score"] // 5
        r = random.randint
        kind = random.choice(["+", "-"] if level == 0 else ["+", "-", "\u00d7"] if level == 1
                             else ["+", "-", "\u00d7", "\u00f7"])
        big = 10 + 10 * min(level, 6)
        if kind == "+":
            a, b = r(1, big), r(1, big)
            ans = a + b
        elif kind == "-":
            a, b = r(1, big), r(1, big)
            a, b = max(a, b), min(a, b)
            ans = a - b
        elif kind == "\u00d7":
            a, b = r(2, 5 + min(level, 7)), r(2, 9)
            ans = a * b
        else:
            b, ans = r(2, 9), r(2, 5 + min(level, 7))
            a = b * ans
        opts = {ans}
        while len(opts) < 4:
            cand = ans + random.choice([-1, 1]) * r(1, max(3, ans // 4 + 2))
            if cand >= 0:
                opts.add(cand)
        opts = list(opts)
        random.shuffle(opts)
        mt.update({"q": "%d %s %d" % (a, kind, b), "ans": ans, "opts": opts, "res": None, "pick": None})
        for i, v in enumerate(opts):
            btn = self.B["ans%d" % i]
            btn.label = "%d.   %d" % (i + 1, v)
            btn.visible = True
            btn.enabled = True

    def step_math(self, dt):
        mt = self.mt
        if mt["phase"] == "ready":
            if self._countdown(mt, dt, "Click the right answer (or press 1, 2, 3, 4)"):
                mt["phase"] = "play"
                self.math_new()
        elif mt["phase"] == "play":
            mt["left"] -= dt
            if mt["lock"] > 0:
                mt["lock"] -= dt
                if mt["lock"] <= 0:
                    self.math_new()
            if mt["left"] <= 0:
                self.math_finish()

    def math_pick(self, i):
        mt = self.mt
        if mt.get("phase") != "play" or mt["lock"] > 0 or not 0 <= i < len(mt["opts"]):
            return
        mt["pick"] = i
        if mt["opts"][i] == mt["ans"]:
            mt["streak"] += 1
            gain = 1 + (2 if mt["streak"] % 5 == 0 else 0)
            mt["score"] += gain
            mt["res"] = "ok"
            mt["lock"] = 0.3
            self.add_float(self.play_rect().center().x(), 0.27 * self.H, "+%d" % gain, GREEN)
            self.mood("surprised", 500, "normal")
        else:
            mt["streak"] = 0
            mt["res"] = "bad"
            mt["lock"] = 1.0
            self.add_float(self.play_rect().center().x(), 0.27 * self.H, "%s = %d" % (mt["q"], mt["ans"]), RED, 0.04)
            self.mood("dance", 900, "normal")
        for k in range(4):
            self.B["ans%d" % k].enabled = False

    def math_finish(self):
        mt = self.mt
        mt["phase"] = "over"
        for k in range(4):
            self.B["ans%d" % k].visible = False
        new_best = self._new_best("math_best", mt["score"])
        self.set_msg("Time's up!  Score: %d" % mt["score"],
                     "\U0001F31F New best!" if new_best else "Best: %d" % self.stats["math_best"],
                     YELLOW, y=0.45, size=1.2)
        self.mood("love" if mt["score"] >= 15 else "normal", 3000, "normal")
        if mt["score"] >= 15:
            self.rain = 2.0
        self._show_over_buttons()

    def draw_math(self, p):
        mt = self.mt
        H = self.H
        pr = self.play_rect()
        low = mt["phase"] == "play" and mt["left"] <= 5
        left = MATH_SECONDS if mt["phase"] == "ready" else max(0.0, mt["left"])
        self._pills(p, [("SCORE", str(mt["score"]), GREEN), ("TIME", "%d" % math.ceil(left), RED if low else ORANGE),
                        ("STREAK", str(mt["streak"]), YELLOW)])
        if mt["phase"] != "play":
            return
        color = GREEN if mt["res"] == "ok" else RED if mt["res"] == "bad" else WHITE
        self.draw_text(p, "%s = ?" % mt["q"], pr.center().x(), 0.36 * H, 0.1 * H, color, shadow=True)
        if mt["res"] is not None:
            for i, v in enumerate(mt["opts"]):
                r = self.B["ans%d" % i].rect
                if v == mt["ans"] or i == mt["pick"]:
                    c = GREEN if v == mt["ans"] else RED
                    p.setPen(QPen(c, max(4.0, 0.006 * H)))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(r.adjusted(-6, -6, 6, 6), r.height() * 0.25, r.height() * 0.25)
        self._help(p, "Every 5 right answers in a row = +2 bonus")

    # ------------------------------------------------------------------
    # 8. SNAKE
    # ------------------------------------------------------------------
    def go_snake(self):
        self._game_start("snake")
        pr = self.play_rect()
        H = self.H
        cell = int(max(14, min(pr.width() / 22.0, (pr.height() - 0.08 * H) / 14.0)))
        cols = min(26, int(pr.width() // cell))
        rows = min(18, int((pr.height() - 0.08 * H) // cell))
        mid = (cols // 2, rows // 2)
        self.sn = {"phase": "ready", "cell": cell, "cols": cols, "rows": rows,
                   "body": [(mid[0] - i, mid[1]) for i in range(4)], "dir": (1, 0), "queue": [],
                   "acc": 0.0, "step": SNAKE_START_STEP, "score": 0, "food": None, "eat_t": -9.0}
        self.snake_food()
        self._over_buttons()
        self.set_msg("Press an arrow key to start", "Arrow keys or W A S D.  Eat the fish, don't hit the walls!",
                     YELLOW, y=0.12, size=0.75)
        self.mood("happy")

    def snake_origin(self):
        sn = self.sn
        pr = self.play_rect()
        return pr.center().x() - sn["cols"] * sn["cell"] / 2.0, pr.top() + 0.03 * self.H

    def snake_food(self):
        sn = self.sn
        free = [(x, y) for x in range(sn["cols"]) for y in range(sn["rows"]) if (x, y) not in sn["body"]]
        sn["food"] = random.choice(free) if free else None

    def snake_key(self, key, text):
        sn = self.sn
        dirs = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        letters = {"a": (-1, 0), "d": (1, 0), "w": (0, -1), "s": (0, 1)}
        d = dirs.get(key) or letters.get(text)
        if d is None or sn.get("phase") == "over":
            return
        if sn["phase"] == "ready":
            sn["phase"] = "play"
            self.set_msg("")
        last = sn["queue"][-1] if sn["queue"] else sn["dir"]
        if d != last and d != (-last[0], -last[1]) and len(sn["queue"]) < 3:
            sn["queue"].append(d)

    def step_snake(self, dt):
        sn = self.sn
        if sn["phase"] != "play":
            return
        sn["acc"] += dt
        while sn["acc"] >= sn["step"] and sn["phase"] == "play":
            sn["acc"] -= sn["step"]
            if sn["queue"]:
                sn["dir"] = sn["queue"].pop(0)
            hx, hy = sn["body"][0]
            head = (hx + sn["dir"][0], hy + sn["dir"][1])
            eat = head == sn["food"]
            body = sn["body"] if eat else sn["body"][:-1]
            if not (0 <= head[0] < sn["cols"] and 0 <= head[1] < sn["rows"]) or head in body:
                self.snake_finish()
                return
            sn["body"].insert(0, head)
            if eat:
                sn["score"] += 1
                sn["eat_t"] = self.t_total
                sn["step"] = max(0.055, SNAKE_START_STEP - sn["score"] * 0.004)
                x0, y0 = self.snake_origin()
                c = sn["cell"]
                self.burst(x0 + (head[0] + 0.5) * c, y0 + (head[1] + 0.5) * c, "spark", 8, [YELLOW, WHITE, ORANGE])
                self.mood("happy", 600, "normal")
                self.snake_food()
                if sn["food"] is None:
                    self.snake_finish()
                    return
            else:
                sn["body"].pop()

    def snake_finish(self):
        sn = self.sn
        sn["phase"] = "over"
        new_best = self._new_best("snake_best", sn["score"])
        self.set_msg("Game over!  Score: %d" % sn["score"],
                     "\U0001F31F New best!" if new_best else "Best: %d" % self.stats["snake_best"],
                     YELLOW, y=0.45, size=1.2)
        self.mood("surprised", 1200, "love" if sn["score"] >= 10 else "normal")
        if sn["score"] >= 10:
            self.rain = 2.0
            self.meow()
        self._show_over_buttons()

    def draw_snake(self, p):
        sn = self.sn
        self._pills(p, [("SCORE", str(sn["score"]), GREEN), ("LENGTH", str(len(sn["body"])), ORANGE)])
        if sn["phase"] == "over":
            return
        x0, y0 = self.snake_origin()
        c = float(sn["cell"])
        board = QRectF(x0, y0, sn["cols"] * c, sn["rows"] * c)
        p.setPen(QPen(with_alpha(WHITE, 0.25), 2))
        p.setBrush(QColor(20, 14, 34, 200))
        p.drawRoundedRect(board.adjusted(-6, -6, 6, 6), 12, 12)
        p.setPen(QPen(with_alpha(WHITE, 0.04), 1))
        for x in range(1, sn["cols"]):
            p.drawLine(QPointF(x0 + x * c, y0), QPointF(x0 + x * c, board.bottom()))
        for y in range(1, sn["rows"]):
            p.drawLine(QPointF(x0, y0 + y * c), QPointF(board.right(), y0 + y * c))
        if sn["food"] is not None:
            fx, fy = sn["food"]
            wob = 1.0 + 0.08 * math.sin(self.t_total * 6)
            self.draw_text(p, "\U0001F41F", x0 + (fx + 0.5) * c, y0 + (fy + 0.5) * c, c * 0.95 * wob, WHITE, emoji=True)
        n = len(sn["body"])
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n - 1, 0, -1):                     # body: tail first, so the head is on top
            bx, by = sn["body"][i]
            k = i / float(max(1, n - 1))
            col = QColor(int(lerp(255, 255, k)), int(lerp(150, 214, k)), int(lerp(80, 140, k)))
            p.setBrush(col)
            r = c * (0.46 - 0.12 * k)
            p.drawEllipse(QPointF(x0 + (bx + 0.5) * c, y0 + (by + 0.5) * c), r, r)
        hx, hy = sn["body"][0]
        self.snake_head(p, x0 + (hx + 0.5) * c, y0 + (hy + 0.5) * c, c, sn["dir"])
        if sn["phase"] == "play":
            self._help(p, "Arrow keys or W A S D")

    def snake_head(self, p, x, y, c, d):
        """A little cat face that looks where it goes."""
        r = c * 0.56
        ang = math.degrees(math.atan2(d[1], d[0])) + 90.0
        p.save()
        p.translate(x, y)
        p.rotate(ang)
        p.setPen(QPen(DARK, max(1.5, c * 0.06)))
        p.setBrush(QColor(255, 150, 80))
        for sx in (-1, 1):                                 # ears
            ear = QPainterPath()
            ear.moveTo(sx * r * 0.85, -r * 0.2)
            ear.lineTo(sx * r * 0.65, -r * 1.15)
            ear.lineTo(sx * r * 0.1, -r * 0.75)
            ear.closeSubpath()
            p.drawPath(ear)
        p.drawEllipse(QPointF(0, 0), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(WHITE)
        for sx in (-1, 1):
            p.drawEllipse(QPointF(sx * r * 0.38, -r * 0.2), r * 0.24, r * 0.28)
        p.setBrush(DARK)
        for sx in (-1, 1):
            p.drawEllipse(QPointF(sx * r * 0.38, -r * 0.3), r * 0.12, r * 0.14)
        p.setBrush(PINK)
        p.drawEllipse(QPointF(0, r * 0.25), r * 0.12, r * 0.09)
        p.restore()

    def text_font(self, px, bold=True, emoji=False):
        f = QFont()
        f.setFamilies([EMOJI_FONT] if emoji else [TEXT_FONT, EMOJI_FONT])
        f.setPixelSize(max(1, int(px)))
        f.setBold(bold)
        return f

    def draw_text(self, p, s, cx, cy, px, color=WHITE, bold=True, shadow=False, emoji=False, angle=0.0):
        p.save()
        p.translate(cx, cy)
        if angle:
            p.rotate(angle)
        p.setFont(self.text_font(px, bold, emoji))
        rect = QRectF(-1500, -400, 3000, 800)
        if shadow:
            p.setPen(QColor(0, 0, 0, 150))
            p.drawText(rect.translated(0, max(2, px * 0.05)), Qt.AlignmentFlag.AlignCenter, s)
        p.setPen(color)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, s)
        p.restore()

    def draw_hand(self, p, emoji, x, y, size, flip, glow, scale, angle):
        p.save()
        p.translate(x, y)
        if glow is not None:
            rg = QRadialGradient(QPointF(0, 0), size * 0.95)
            rg.setColorAt(0, with_alpha(glow, 0.65))
            rg.setColorAt(1, with_alpha(glow, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rg)
            p.drawEllipse(QPointF(0, 0), size * 0.95, size * 0.95)
        p.scale(-scale if flip else scale, scale)
        if angle:
            p.rotate(angle)
        self.draw_text(p, emoji, 0, 0, size, WHITE, emoji=True)
        p.restore()

    def pill(self, p, cx, cy, label, value, color, emoji_value=False):
        H = self.H
        w, h = 0.24 * H, 0.115 * H
        rr = QRectF(cx - w / 2, cy - h / 2, w, h)
        p.setPen(QPen(with_alpha(color, 0.9), 3))
        p.setBrush(QColor(20, 14, 34, 190))
        p.drawRoundedRect(rr, h * 0.35, h * 0.35)
        self.draw_text(p, label, cx, cy - h * 0.28, h * 0.2, with_alpha(color, 1.0))
        self.draw_text(p, value, cx, cy + h * 0.12, h * 0.42 if not emoji_value else h * 0.34,
                       WHITE, emoji=emoji_value)

    def draw_button(self, p, b):
        if not b.visible:
            return
        r = b.rect
        hv = b.hover
        sc = 1.0 + 0.07 * hv - 0.06 * b.press
        p.save()
        p.translate(r.center().x(), r.center().y() - hv * 0.008 * self.H)
        p.scale(sc, sc)
        rr = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        rad = min(r.width(), r.height()) * 0.2
        p.setOpacity(1.0 if b.enabled else 0.4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(rr.translated(0, r.height() * 0.06), rad, rad)
        if b.kind == "small":
            p.setPen(QPen(with_alpha(WHITE, 0.5 + 0.4 * hv), 2))
            p.setBrush(QColor(20 + int(40 * hv), 14 + int(20 * hv), 34 + int(40 * hv), 215))
            p.drawRoundedRect(rr, rad, rad)
            self.draw_text(p, b.label, 0, 0, r.height() * 0.42, WHITE)
        elif b.kind == "wide":
            g = QLinearGradient(rr.topLeft(), rr.bottomLeft())
            g.setColorAt(0, QColor(255, 190, 120).lighter(100 + int(12 * hv)))
            g.setColorAt(1, QColor(255, 130, 90).lighter(100 + int(12 * hv)))
            p.setPen(QPen(QColor(255, 235, 215), 3))
            p.setBrush(g)
            p.drawRoundedRect(rr, rad, rad)
            self.draw_text(p, b.label, 0, 0, r.height() * 0.4, WHITE, shadow=True)
        else:
            g = QLinearGradient(rr.topLeft(), rr.bottomLeft())
            g.setColorAt(0, QColor(255, 247, 238).lighter(100 + int(6 * hv)))
            g.setColorAt(1, QColor(255, 217, 189).lighter(100 + int(6 * hv)))
            p.setPen(QPen(QColor(236, 198, 166).lighter(100 + int(10 * hv)), 3))
            p.setBrush(g)
            p.drawRoundedRect(rr, rad, rad)
            self.draw_text(p, b.icon, 0, -r.height() * 0.17, r.height() * 0.4, DARK, emoji=True)
            self.draw_text(p, b.label, 0, r.height() * 0.24, min(r.height() * 0.13, r.width() * 0.085), DARK)
            if b.hint:
                self.draw_text(p, b.hint, 0, r.height() * 0.4, r.height() * 0.09, QColor(150, 120, 100), bold=False)
        p.restore()

    def draw_menu(self, p):
        H = self.H
        mid = self.play_rect().center().x()
        pop = ease_out_back(min(1.0, self.t_total / 0.6))
        p.save()
        p.translate(mid, 0.075 * H)
        p.scale(0.5 + 0.5 * pop, 0.5 + 0.5 * pop)
        self.draw_text(p, "\U0001F431 Cat Arcade", 0, 0, 0.08 * H, WHITE, shadow=True)
        p.restore()
        self.draw_text(p, "Pick a game to play with me!  (or click me to pet me)", mid, 0.15 * H,
                       0.03 * H, with_alpha(CREAM, 0.9), bold=False, shadow=True)
        st = self.stats

        def best(key, unit=""):
            return "Best: %d%s" % (st[key], unit) if st[key] else "Not played yet"
        subs = {"g_rps": "Won %d  -  Lost %d" % (st["rps_w"], st["rps_l"]),
                "g_treat": best("treat_best"), "g_cups": best("cups_best"),
                "g_mem": best("mem_best", " moves"), "g_whack": best("whack_best"),
                "g_type": best("type_best", " WPM"), "g_math": best("math_best"),
                "g_snake": best("snake_best")}
        for key, text in subs.items():
            b = self.B.get(key)
            if b is not None and b.visible:
                r = b.rect
                self.draw_text(p, text, r.center().x(), r.bottom() + 0.025 * H, 0.022 * H,
                               with_alpha(CREAM, 0.8), bold=False, shadow=True)

    def draw_message(self, p):
        if not self.msg_main and not self.msg_sub:
            return
        W, H = self.W, self.H
        if self.mgr.spot == "left":                 # the game is on the right of the cat
            mid, y = self.play_rect().center().x(), self.msg_y * H
        else:
            mid, y = W / 2, max(self.msg_y * H, self.cat_rect().bottom() + 0.045 * H)
        sc = 0.6 + 0.4 * ease_out_back(self.msg_t / 0.35)
        if self.msg_main:
            p.save()
            p.translate(mid, y)
            p.scale(sc, sc)
            self.draw_text(p, self.msg_main, 0, 0, 0.05 * H * self.msg_size, self.msg_col, shadow=True)
            p.restore()
        if self.msg_sub:
            self.draw_text(p, self.msg_sub, mid, y + 0.058 * H, 0.027 * H,
                           QColor(255, 235, 215), bold=False, shadow=True)

    def paintEvent(self, event):
        W, H = self.W, self.H
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor(16, 10, 28, 178))
        cr = self.cat_rect()
        spot = QRadialGradient(cr.center(), H * 0.62)
        spot.setColorAt(0, QColor(255, 170, 110, 120))
        spot.setColorAt(0.6, QColor(255, 140, 120, 36))
        spot.setColorAt(1, QColor(255, 170, 110, 0))
        p.fillRect(self.rect(), spot)
        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, ph, sp in self.stars:
            a = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(self.t_total * sp + ph))
            p.setBrush(with_alpha(WHITE, a))
            p.drawEllipse(QPointF(sx * W, sy * H), 2.2, 2.2)

        draw = getattr(self, "draw_" + self.screen_name, None)
        if draw is not None:
            draw(p)

        self.draw_message(p)
        for b in self.buttons:
            self.draw_button(p, b)

        for pt in self.particles:
            k = 1.0 - pt["life"] / pt["max"]
            alpha = clamp(k * 1.6)
            p.save()
            p.translate(pt["x"], pt["y"])
            p.rotate(pt["rot"])
            if pt["kind"] == "confetti":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pt["color"], alpha))
                p.drawRect(QRectF(-pt["size"], -pt["size"] * 0.5, pt["size"] * 2, pt["size"]))
            elif pt["kind"] == "heart":
                p.setOpacity(alpha)
                self.draw_text(p, "\u2764\ufe0f", 0, 0, pt["size"] * 2.6, WHITE, emoji=True)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pt["color"], alpha))
                p.drawEllipse(QPointF(0, 0), pt["size"] * 0.7, pt["size"] * 0.7)
            p.restore()
        for f in self.floats:
            k = f["t"] / f["life"]
            p.save()
            p.setOpacity(clamp(1.0 - max(0.0, k - 0.6) / 0.4))
            sc = 0.7 + 0.5 * ease_out_back(k * 3)
            p.translate(f["x"], f["y"])
            p.scale(sc, sc)
            self.draw_text(p, f["text"], 0, 0, f["size"] * H, f["color"], shadow=True)
            p.restore()
        p.end()