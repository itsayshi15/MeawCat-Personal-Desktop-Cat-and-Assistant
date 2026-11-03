"""
kitten.py - a little kitten that visits the cat now and then
=============================================================
* Every so often (when you are at the PC and the cat is at home on the taskbar) a small kitten
  walks in from the edge of the screen, trots over to the cat, sits down and says hello with
  hearts, plays a little (happy jumps, paws up), then turns round and trots away again.
* Tray > Play with the cat > "Invite the kitten" calls it right now.
* Tray > Play with the cat > "Kitten visits" switches the surprise visits on or off.
* The kitten is drawn by code in the same style as the big cat (soft fur, dark outline,
  big shiny eyes), with a whole body: four legs that really walk, a curly tail, ears that
  twitch, eyes that blink and look up at the big cat. Each visit it has another fur colour.
"""
import math
import random
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import (QColor, QGuiApplication, QPainter, QPainterPath, QPainterPathStroker,
                           QPen, QTransform)
from PySide6.QtWidgets import QWidget

KITTEN_SCALE = 0.55            # kitten length compared with the cat's width
MIN_KITTEN = 56                # smallest kitten (pixels)
VISIT_CHECK_SECONDS = 60       # how often the kitten thinks about visiting
VISIT_CHANCE = 0.06            # chance per check (about one visit an hour while you work)
VISIT_MIN_GAP = 20 * 60        # never two visits within this many seconds
WALK_SPEED = 1.15              # kitten lengths per second
STEP_RATE = 24.0               # how fast the legs move while walking (radians per second)
TURN_SECONDS = 0.28            # time to turn round
GREET_SECONDS = 3.2
PLAY_SECONDS = 4.0

# The kitten is drawn in "units": 1 unit = 1/100 of its length. (0, 0) = the ground under its
# middle. It is drawn facing right and mirrored when it walks to the left.
SIDE_ROOM = 30.0               # units of free room left and right (tail, whiskers, turning)
TOP_ROOM = 205.0               # units of room above the ground (ears, jumps, hearts)
BELOW = 5.0                    # units below the ground line (soft shadow)

FURS = [  # name, fur, tabby stripes (None = plain), ear / nose pink
    ("ginger", QColor(255, 196, 136), QColor(236, 142, 72), QColor(255, 160, 168)),
    ("grey", QColor(204, 207, 218), QColor(150, 155, 176), QColor(255, 170, 186)),
    ("cream", QColor(255, 236, 210), None, QColor(255, 168, 182)),
    ("blue-grey", QColor(182, 200, 228), None, QColor(255, 172, 196)),
    ("pink", QColor(255, 212, 226), None, QColor(255, 140, 172)),
    ("brown tabby", QColor(222, 190, 156), QColor(160, 118, 82), QColor(255, 160, 168)),
]
DARK = QColor(38, 38, 38)
WHITE = QColor(255, 255, 255)
HEART = QColor(255, 82, 120)
TONGUE = QColor(255, 120, 140)
CHEEK = QColor(255, 130, 155, 120)

# body parts (units, standing, facing right)
BODY_C = QPointF(-6.0, -29.0)
BODY_RX, BODY_RY = 29.0, 15.5
HEAD_C = QPointF(21.0, -55.0)
HEAD_RX, HEAD_RY = 26.5, 23.0
FACE_DX = 2.5                  # the face looks a little to the front
SIT_PIVOT = QPointF(-30.0, -15.0)
SIT_ANGLE = 15.0               # degrees the body tips back when the kitten sits
TAIL_BASE = QPointF(-31.0, -33.0)
# hip of each leg, and the walking phase it moves in (diagonal legs move together)
LEGS = (("back", "far", QPointF(-22.0, -24.0), 0.0),
        ("front", "far", QPointF(9.0, -24.0), math.pi),
        ("back", "near", QPointF(-15.0, -23.0), math.pi),
        ("front", "near", QPointF(16.0, -23.0), 0.0))
LEG_W = 8.5                    # leg thickness (units)
PAW_RX, PAW_RY = 5.4, 3.7


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def lerp(a, b, k):
    return a + (b - a) * k


def make_pen(color, width):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _stroke(path, width):
    """A thick round-ended shape that follows the path (used for the legs and the tail)."""
    s = QPainterPathStroker()
    s.setWidth(width)
    s.setCapStyle(Qt.PenCapStyle.RoundCap)
    s.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return s.createStroke(path).simplified()


def _outlined(p, path, fill, ol):
    p.setPen(make_pen(DARK, ol))
    p.setBrush(fill)
    p.drawPath(path)


# ----------------------------------------------------------------------
# drawing (no window needed: draw_kitten can paint on any QPainter)
# ----------------------------------------------------------------------
def default_pose():
    return {"gait": 0.0, "stride": 0.0, "bob": 0.0, "tuck": 0.0, "reach": 0.0, "sit": 0.0,
            "eyes": "open", "blink": 0.0, "look": (1.2, 0.0), "mouth": "w", "tilt": 0.0,
            "wag_speed": 5.0, "wag": 1.0, "ears": (0.0, 0.0), "ol": 2.6}


def tail_path(base, t, speed, amount):
    """A curly tail: it leaves the body backwards and curls up like a question mark.
    The wag runs along it like a wave, so it moves softly instead of like a stick."""
    path = QPainterPath(base)
    x, y = base.x(), base.y()
    ang = math.radians(196.0)
    for i in range(9):
        ang += math.radians(12.5)
        ang += amount * 0.17 * math.sin(t * speed - i * 0.55)
        x += math.cos(ang) * 5.0
        y += math.sin(ang) * 5.0
        path.lineTo(x, y)
    return path


def ear_path(hx, hy, side, twitch):
    """One ear on the head at (hx, hy). side -1 = back ear, +1 = front ear."""
    b1 = QPointF(hx + side * 25.0, hy - 6.0)
    b2 = QPointF(hx + side * 6.0, hy - 21.0)
    tip = QPointF(hx + side * (21.0 - 4.0 * twitch), hy - 37.0 + 3.0 * twitch)
    a = QPointF(lerp(b1.x(), tip.x(), 0.8), lerp(b1.y(), tip.y(), 0.8))
    c = QPointF(lerp(b2.x(), tip.x(), 0.8), lerp(b2.y(), tip.y(), 0.8))
    path = QPainterPath(b1)
    path.lineTo(a)
    path.quadTo(tip, c)
    path.lineTo(b2)
    path.closeSubpath()
    inner = QPainterPath()
    mid = QPointF((b1.x() + b2.x()) / 2.0, (b1.y() + b2.y()) / 2.0 + 2.0)
    for k, pt in enumerate((b1, tip, b2)):
        q = QPointF(lerp(mid.x(), pt.x(), 0.62), lerp(mid.y(), pt.y(), 0.62) + 1.5)
        if k == 0:
            inner.moveTo(q)
        else:
            inner.lineTo(q)
    inner.closeSubpath()
    return path, inner


def draw_kitten(p, pose, fur, t):
    """Paint the kitten facing right. (0, 0) = ground under its middle, units = 1/100 length."""
    _name, col, mark, pink = fur
    ol = pose["ol"]
    sit = pose["sit"]
    shade = col.darker(112)

    # where the body is: lifted by the walk bob, tipped back when sitting
    body = QTransform()
    body.translate(0.0, -pose["bob"])
    body.translate(SIT_PIVOT.x(), SIT_PIVOT.y())
    body.rotate(-SIT_ANGLE * sit)
    body.translate(-SIT_PIVOT.x(), -SIT_PIVOT.y())

    # ---- tail (behind everything)
    tail = tail_path(body.map(TAIL_BASE), t, pose["wag_speed"], pose["wag"])
    _outlined(p, _stroke(tail, 7.0), col, ol)
    if mark is not None:                                        # darker tail tip
        tip = QPainterPath(tail.pointAtPercent(0.78))
        tip.lineTo(tail.pointAtPercent(1.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mark)
        p.drawPath(_stroke(tip, 7.0 - ol * 0.5))

    # ---- legs (far legs first and a bit darker)
    g = pose["gait"]
    amp, lift_h = 7.0 * pose["stride"], 4.5 * pose["stride"]
    for end, side, hip0, off in LEGS:
        hip = body.map(hip0)
        fx = hip0.x() + 1.0 - math.cos(g + off) * amp
        fy = -PAW_RY - max(0.0, math.sin(g + off)) * lift_h
        if end == "back":
            fx += sit * 9.0                                     # sitting: back paws under the body
        else:
            fx -= sit * 2.5
        fy += pose["tuck"] * 6.0 * (-1.0)                       # jumping: legs tucked up
        if end == "front" and pose["reach"] > 0.0:              # playing: front paws reach up
            r = pose["reach"]
            fx = lerp(fx, hip.x() + 10.0, r)
            fy = lerp(fy, hip.y() + 7.0, r)
        leg = QPainterPath(hip)
        leg.lineTo(fx, fy - 1.5)
        shape = _stroke(leg, LEG_W)
        paw = QPainterPath()
        paw.addEllipse(QPointF(fx + 1.2, fy), PAW_RX, PAW_RY)
        shape = shape.united(paw).simplified()
        _outlined(p, shape, shade if side == "far" else col, ol)

    # ---- body
    p.save()
    p.setTransform(body, True)
    bpath = QPainterPath()
    bpath.addEllipse(BODY_C, BODY_RX, BODY_RY)
    _outlined(p, bpath, col, ol)
    if mark is not None:                                        # tabby stripes on the back
        p.save()
        p.setClipPath(bpath)
        p.setPen(make_pen(mark, 3.2))
        for x in (-25.0, -15.0, -5.0, 5.0):
            stripe = QPainterPath(QPointF(x - 1.0, BODY_C.y() - BODY_RY - 2.0))
            stripe.quadTo(x + 3.0, BODY_C.y() - BODY_RY + 5.0, x + 1.0, BODY_C.y() - BODY_RY + 10.0)
            p.drawPath(stripe)
        p.restore()
    p.setPen(Qt.PenStyle.NoPen)                                 # soft lighter belly
    p.setBrush(QColor(255, 255, 255, 70))
    p.drawEllipse(QPointF(BODY_C.x() + 4.0, BODY_C.y() + 7.0), BODY_RX * 0.62, BODY_RY * 0.42)
    p.restore()

    if sit > 0.02:                                              # sitting: round back leg (haunch)
        p.save()
        p.setOpacity(p.opacity() * smooth(sit / 0.6))
        haunch = QPainterPath()
        hc = body.map(QPointF(-19.0, -20.0))
        haunch.addEllipse(QPointF(hc.x(), min(hc.y(), -12.5)), 13.5, 12.5)
        _outlined(p, haunch, col, ol)
        p.restore()

    # ---- head (moves up a little when sitting, tilts when the kitten wonders)
    hx = HEAD_C.x() - 5.0 * sit
    hy = HEAD_C.y() - pose["bob"] * 1.15 - 9.0 * sit
    p.save()
    p.translate(hx, hy)
    p.rotate(pose["tilt"])
    p.translate(-hx, -hy)
    tw_back, tw_front = pose["ears"]
    for side, tw in ((-1, tw_back), (1, tw_front)):
        ear, inner = ear_path(hx + FACE_DX * 0.4, hy, side, tw)
        _outlined(p, ear, col, ol)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pink)
        p.drawPath(inner)
    hpath = QPainterPath()
    hpath.addEllipse(QPointF(hx, hy), HEAD_RX, HEAD_RY)
    _outlined(p, hpath, col, ol)
    fx = hx + FACE_DX
    if mark is not None:                                        # little "M" stripes on the forehead
        p.save()
        p.setClipPath(hpath)
        p.setPen(make_pen(mark, 2.6))
        for dx, top, bot in ((-6.0, -20.0, -13.0), (0.0, -22.5, -14.5), (6.0, -20.0, -13.0)):
            p.drawLine(QPointF(fx + dx, hy + top), QPointF(fx + dx * 0.8, hy + bot))
        p.restore()
    p.setPen(Qt.PenStyle.NoPen)                                 # pink cheeks
    p.setBrush(CHEEK)
    for side in (-1, 1):
        p.drawEllipse(QPointF(fx + side * 15.5, hy + 8.0), 4.4, 2.6)
    _eyes(p, pose, fx, hy)
    _mouth(p, pose, fx, hy, pink)
    wpen = make_pen(DARK, max(0.9, ol * 0.36))                  # whiskers
    p.setPen(wpen)
    for side in (-1, 1):
        sx = fx + side * 18.5
        for dy in (-2.5, 2.5):
            w = QPainterPath(QPointF(sx, hy + 6.5 + dy * 0.3))
            w.quadTo(sx + side * 6.0, hy + 5.5 + dy, sx + side * 12.0, hy + 6.5 + dy * 1.6)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(w)
    p.restore()


def _eyes(p, pose, fx, hy):
    mode = pose["eyes"]
    lx, ly = pose["look"]
    for side in (-1, 1):
        ex, ey = fx + side * 10.5, hy + 0.5
        if mode == "happy":                                     # ^ ^  (like the big cat's happy eyes)
            p.setPen(make_pen(DARK, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            arc = QPainterPath(QPointF(ex - 4.4, ey + 2.0))
            arc.quadTo(ex, ey - 4.6, ex + 4.4, ey + 2.0)
            p.drawPath(arc)
            continue
        sy = max(0.06, 1.0 - pose["blink"])
        if sy < 0.2:                                            # closed for a moment: a soft line
            p.setPen(make_pen(DARK, 1.8))
            p.drawLine(QPointF(ex - 4.2 + lx * 0.4, ey + 0.8), QPointF(ex + 4.2 + lx * 0.4, ey + 0.8))
            continue
        p.save()
        p.translate(ex + lx, ey + ly)
        p.scale(1.0, sy)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(DARK)
        p.drawEllipse(QPointF(0, 0), 4.6, 5.9)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(-1.45, -2.2), 1.55, 1.55)          # big shine
        p.drawEllipse(QPointF(1.55, 1.8), 0.7, 0.7)              # small shine
        p.restore()


def _mouth(p, pose, fx, hy, pink):
    mode = pose["mouth"]
    ny = hy + 7.2
    nose = QPainterPath(QPointF(fx - 1.9, ny - 1.2))             # tiny pink nose
    nose.quadTo(fx, ny - 2.0, fx + 1.9, ny - 1.2)
    nose.quadTo(fx + 0.4, ny + 1.4, fx, ny + 1.4)
    nose.quadTo(fx - 0.4, ny + 1.4, fx - 1.9, ny - 1.2)
    p.setPen(make_pen(pink.darker(125), 0.7))
    p.setBrush(pink)
    p.drawPath(nose)
    if mode in ("open", "smile"):                               # open mouth with a little tongue
        h = 4.2 if mode == "open" else 2.8
        m = QPainterPath(QPointF(fx - 2.8, ny + 2.4))
        m.quadTo(fx, ny + 1.6, fx + 2.8, ny + 2.4)
        m.quadTo(fx + 2.6, ny + 2.4 + h, fx, ny + 2.4 + h)
        m.quadTo(fx - 2.6, ny + 2.4 + h, fx - 2.8, ny + 2.4)
        p.setPen(make_pen(DARK, 1.2))
        p.setBrush(QColor(120, 40, 50))
        p.drawPath(m)
        p.save()
        p.setClipPath(m)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(TONGUE)
        p.drawEllipse(QPointF(fx, ny + 2.4 + h), 2.4, 1.8)
        p.restore()
        return
    w = QPainterPath(QPointF(fx - 3.6, ny + 2.2))               # the little cat mouth  w
    w.quadTo(fx - 1.8, ny + 4.6, fx, ny + 1.6)
    w.quadTo(fx + 1.8, ny + 4.6, fx + 3.6, ny + 2.2)
    p.setPen(make_pen(DARK, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(w)


def draw_heart(p, x, y, size, alpha):
    if alpha <= 0:
        return
    p.save()
    p.setOpacity(alpha)
    p.translate(x, y)
    s = size / 2.0
    path = QPainterPath()
    path.moveTo(0, s * 0.9)
    path.cubicTo(-s * 1.4, -s * 0.1, -s * 0.6, -s * 1.2, 0, -s * 0.45)
    path.cubicTo(s * 0.6, -s * 1.2, s * 1.4, -s * 0.1, 0, s * 0.9)
    p.setPen(QPen(WHITE, max(1.0, size * 0.08)))
    p.setBrush(HEART)
    p.drawPath(path)
    p.restore()


# ----------------------------------------------------------------------
class Kitten:
    """Main_file.pyw creates one. cat needs: cat_w, x(), width(), saved, save_settings(), wake(),
    timed (dict), paused, feed, assistant (dnd, busy(), rps.is_active()), mover.is_home(),
    features (may be None)."""

    def __init__(self, cat, play_sound=None):
        self.cat = cat
        self.play_sound = play_sound
        self.win = _KittenWindow(self)
        self.phase = None             # None, "in", "greet", "play", "out"
        self.t0 = 0.0
        self.x = 0.0                  # left edge of the kitten (window pixels on the screen)
        self.start_x = 0.0
        self.target_x = 0.0
        self.exit_x = 0.0
        self.dir = 1                  # where it wants to look: 1 = right, -1 = left
        self.face = 1.0               # where it looks now (turns smoothly between -1 and 1)
        self.gait = 0.0
        self.speed = 0.0
        self.stride = 0.0
        self.sit = 0.0
        self.last_visit = time.time()
        self.last_t = time.perf_counter()
        self.fur = FURS[0]
        self.kw = 60
        self.hearts = []
        self.blink_at = 0.0
        self.next_blink = 0.0
        self.twitch_at = 0.0
        self.twitch_ear = 1
        self.next_twitch = 0.0
        self.timer = QTimer(cat)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.check_timer = QTimer(cat)
        self.check_timer.setInterval(VISIT_CHECK_SECONDS * 1000)
        self.check_timer.timeout.connect(self.maybe_visit)
        self.check_timer.start()

    # -- settings / state ---------------------------------------------------------------
    def enabled(self):
        return bool(self.cat.saved.get("kitten_visits", True))

    def set_enabled(self, value):
        self.cat.saved["kitten_visits"] = bool(value)
        self.cat.save_settings()

    def active(self):
        return self.phase is not None

    def unit(self):
        return self.kw / 100.0

    def _cat_free(self):
        cat = self.cat
        a = cat.assistant
        if cat.paused or a.dnd or a.busy() or getattr(cat, "big_mode", False) or cat.feed is not None:
            return False
        try:
            if a.rps.is_active():
                return False
        except Exception:
            pass
        mover = getattr(cat, "mover", None)
        return mover is None or mover.is_home()

    def maybe_visit(self):
        if not self.enabled() or self.active() or not self._cat_free():
            return
        if time.time() - self.last_visit < VISIT_MIN_GAP:
            return
        f = getattr(self.cat, "features", None)
        if f is not None and not f._user_active(60):
            return
        if random.random() < VISIT_CHANCE:
            self.visit()

    # -- a visit ------------------------------------------------------------------------
    def visit(self, manual=False):
        if self.active():
            return
        if not self._cat_free():
            f = getattr(self.cat, "features", None)
            if manual and f is not None:
                f.say("The kitten can only visit when I am at home on the taskbar and not busy.", 4.0)
            return
        self._prepare()
        a = QGuiApplication.primaryScreen().availableGeometry()
        cat = self.cat
        side = self.win.side_px()
        left_room = cat.x() - a.x()
        right_room = a.x() + a.width() - (cat.x() + cat.width())
        gap = self.kw * 0.12
        if left_room >= right_room:                  # come from the left, stop left of the cat
            self.start_x = a.x() - self.kw - side - 4
            self.target_x = max(a.x() + 4, cat.x() - self.kw - gap)
            self.dir = 1
        else:                                        # come from the right
            self.start_x = a.x() + a.width() + side + 4
            self.target_x = min(a.x() + a.width() - self.kw - 4, cat.x() + cat.width() + gap)
            self.dir = -1
        self.face = float(self.dir)
        self.exit_x = self.start_x
        self.x = self.start_x
        self.hearts = []
        self.sit = self.stride = self.speed = 0.0
        now = time.perf_counter()
        self.phase, self.t0 = "in", now
        self.next_blink = now + random.uniform(1.0, 2.5)
        self.next_twitch = now + random.uniform(1.5, 3.5)
        self.last_visit = time.time()
        self.last_t = now
        self.cat.wake()
        self.win.place()
        self.win.show()
        self.win.raise_()
        self.timer.start()

    def _prepare(self):
        """Size and colour for this visit."""
        self.fur = random.choice(FURS)
        self.kw = max(MIN_KITTEN, int(self.cat.cat_w * KITTEN_SCALE))
        u = self.unit()
        self.win.setFixedSize(int(math.ceil(self.kw + 2 * SIDE_ROOM * u)),
                              int(math.ceil((TOP_ROOM + BELOW) * u)))

    def stop(self):
        self.phase = None
        self.timer.stop()
        self.win.hide()

    def _sound(self, kind):
        if self.play_sound is not None and self.cat.saved.get("meow", True):
            self.play_sound(kind)

    def tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.last_t)
        self.last_t = now
        if self.phase is None:
            return
        cat = self.cat
        mover = getattr(cat, "mover", None)
        away = mover is not None and not mover.is_home()          # the cat was picked up / thrown
        if (cat.paused or getattr(cat, "big_mode", False) or away) and self.phase != "out":
            self._leave(now)
        el = now - self.t0
        if self.phase in ("in", "out"):
            goal = self.target_x if self.phase == "in" else self.exit_x
            dist = goal - self.x
            want = 1 if dist > 0 else -1
            if self.phase == "out" and want != self.dir:
                self.dir = want
            turning = abs(self.face - self.dir) > 0.05
            self.speed = 0.0 if turning else min(1.0, abs(dist) / (0.6 * self.kw) + 0.35)
            step = WALK_SPEED * self.kw * dt * self.speed
            self.gait += dt * STEP_RATE * self.speed
            if abs(dist) <= step or (abs(dist) < 0.5 and not turning):
                self.x = goal
                if self.phase == "in":
                    self._greet(now)
                else:
                    self.stop()
                    return
            else:
                self.x += step if dist > 0 else -step
        elif self.phase == "greet":
            cat.wake()
            if el >= GREET_SECONDS:
                self.phase, self.t0 = "play", now
                cat.timed["playful"] = time.perf_counter() + PLAY_SECONDS + 0.5
                self._sound("chirp")
        elif self.phase == "play":
            cat.wake()
            if el >= PLAY_SECONDS:
                self._leave(now)
                cat.timed["happy"] = time.perf_counter() + 2.0
                self._sound("mew")
        # smooth things: turning round, sitting down, legs slowing down
        step = dt * 2.0 / TURN_SECONDS
        self.face = max(-1.0, min(1.0, self.face + max(-step, min(step, self.dir - self.face))))
        self.sit += ((1.0 if self.phase == "greet" else 0.0) - self.sit) * min(1.0, dt * 7.0)
        self.stride += (self.speed - self.stride) * min(1.0, dt * 10.0)
        if now >= self.next_blink:
            self.blink_at = now
            self.next_blink = now + random.uniform(2.2, 5.0)
        if now >= self.next_twitch:
            self.twitch_at = now
            self.twitch_ear = random.choice((-1, 1))
            self.next_twitch = now + random.uniform(2.5, 6.0)
        for h in self.hearts:
            h["t"] += dt
        self.hearts = [h for h in self.hearts if h["t"] < h["life"]]
        self.win.place()
        self.win.update()

    def _greet(self, now):
        cat = self.cat
        self.phase, self.t0 = "greet", now
        self.speed = 0.0
        self.dir = 1 if cat.x() + cat.width() / 2.0 > self.x + self.kw / 2.0 else -1   # look at the cat
        self._sound("mew")
        cat.timed["love"] = time.perf_counter() + GREET_SECONDS + 0.5
        for k in range(5):
            QTimer.singleShot(300 + 260 * k, self._add_heart)

    def _leave(self, now):
        self.phase, self.t0 = "out", now
        self.dir = 1 if self.exit_x > self.x else -1

    def _add_heart(self):
        if self.phase is None:
            return
        self.hearts.append({"t": 0.0, "life": 1.7, "dx": random.uniform(-14.0, 14.0),
                            "sway": random.uniform(0, 6.28), "size": random.uniform(10.0, 15.0)})

    # -- what the drawing needs right now -------------------------------------------------
    def hop(self, now):
        """(jump height in units, squash) for the whole kitten."""
        if self.phase != "play":
            return 0.0, 1.0
        el = now - self.t0
        k = abs(math.sin(el * 5.0))                              # happy little jumps
        fade = smooth(el / 0.3) * smooth((PLAY_SECONDS - el) / 0.3)
        k *= fade
        sq = 1.0 + 0.07 * (k - 0.35)                              # stretch up, squash on landing
        return 22.0 * k, sq

    def pose(self, now):
        ps = default_pose()
        u = self.unit()
        ps["ol"] = max(2.4, 1.7 / u)                              # outline about as thick as the big cat's
        ps["gait"] = self.gait
        ps["stride"] = self.stride
        ps["sit"] = self.sit
        ps["bob"] = 1.3 * self.stride * abs(math.sin(self.gait))
        el = now - self.t0
        b = (now - self.blink_at) / 0.17
        ps["blink"] = math.sin(math.pi * b) if 0.0 <= b < 1.0 else 0.0
        tw = (now - self.twitch_at) / 0.3
        tw = math.sin(math.pi * tw) if 0.0 <= tw < 1.0 else 0.0
        ps["ears"] = (tw, 0.0) if self.twitch_ear < 0 else (0.0, tw)
        if self.phase == "greet":
            ps["look"] = (1.3, -1.8)                              # looks up at the big cat
            ps["tilt"] = -9.0 * smooth((el - 0.8) / 0.5) * (1.0 - smooth((el - 2.2) / 0.4))
            ps["wag_speed"], ps["wag"] = 4.0, 0.9
            if el < 0.65 or 0.95 < el < 1.35:
                ps["mouth"] = "open"                              # mew!
            if el > 2.1:
                ps["eyes"], ps["mouth"] = "happy", "smile"
        elif self.phase == "play":
            hop, _ = self.hop(now)
            k = hop / 22.0
            ps["tuck"] = k
            ps["reach"] = smooth(k / 0.7)
            ps["eyes"], ps["mouth"] = "happy", "smile"
            ps["wag_speed"], ps["wag"] = 10.0, 1.5
        elif self.phase in ("in", "out"):
            ps["wag_speed"], ps["wag"] = 6.0, 0.8 + 0.4 * self.stride
        return ps


class _KittenWindow(QWidget):
    """The kitten's own small see-through window. Clicks go through it."""

    def __init__(self, kitten):
        super().__init__()
        self.k = kitten
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def side_px(self):
        return int(round(SIDE_ROOM * self.k.unit()))

    def ground(self):
        return self.height() - BELOW * self.k.unit()

    def place(self):
        k = self.k
        a = QGuiApplication.primaryScreen().availableGeometry()
        y = int(round(a.y() + a.height() - self.ground()))    # the kitten's paws stand on the taskbar
        x = int(round(k.x)) - self.side_px()
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def paintEvent(self, event):
        k = self.k
        if k.phase is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_kitten(p, time.perf_counter())
        p.end()

    def paint_kitten(self, p, now):
        k = self.k
        u = k.unit()
        hop, sq = k.hop(now)
        pose = k.pose(now)
        cx = self.side_px() + k.kw / 2.0
        gy = self.ground()
        p.save()
        p.translate(cx, gy)
        p.scale(u, u)
        lift = hop / 22.0                                       # soft shadow on the taskbar edge
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(55 * (1.0 - 0.55 * lift))))
        p.drawEllipse(QPointF(0.0, 0.5), 31.0 * (1.0 - 0.3 * lift), 3.2 * (1.0 - 0.3 * lift))
        p.scale(k.face if abs(k.face) > 0.04 else 0.04, 1.0)   # face left or right (turns smoothly)
        p.translate(0.0, -hop)
        p.scale(1.0 / sq, sq)
        draw_kitten(p, pose, k.fur, now)
        p.restore()
        head_x = cx + (HEAD_C.x() - 5.0 * k.sit) * k.face * u
        head_top = gy - (hop + 80.0 + 9.0 * k.sit) * u
        for heart in k.hearts:                                  # hearts float up from the head
            prog = heart["t"] / heart["life"]
            size = heart["size"] * u
            x = head_x + heart["dx"] * u + math.sin(heart["sway"] + prog * 6.0) * 6.0 * u
            y = head_top - prog * 70.0 * u
            alpha = min(1.0, prog / 0.15) * min(1.0, (1.0 - prog) / 0.35)
            draw_heart(p, x, y, size, alpha)
