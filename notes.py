"""
notes.py - sticky notes for Peeking Cat
========================================
* As many notes as you like, each in its own little window on the desktop.
* 7 colours (click the coloured dot in a note).
* Pin a note (the pin button, or double-click the top strip): it stays on top of every
  other window. Unpinned notes behave like normal windows and can go behind other programs.
* Notes & search window: find a note by any word in it, filter by colour, open, delete.
* Everything is saved by itself in notes.json (text, colour, pin, place and size), so the
  notes come back exactly where they were after a restart.
* The old single "Quick sticky note" (sticky_notes.json) is moved into the first note once.
"""
import json
import os
import shutil
import time
from datetime import datetime

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QSizeGrip, QToolButton, QVBoxLayout, QWidget)

NOTES_FILE = "notes.json"
LEGACY_FILE = "sticky_notes.json"      # the old single sticky note
SAVE_DELAY_MS = 600                    # save shortly after you stop typing / moving
NOTE_W, NOTE_H = 260, 230              # size of a new note
MARGIN = 7                             # soft shadow around the paper

# name, paper colour, strip / accent colour
COLORS = [("Yellow", "#fff4a8", "#f2c84b"), ("Pink", "#ffd6e5", "#f07aa2"),
          ("Green", "#d7f5d2", "#5cbc66"), ("Blue", "#d6e9ff", "#5b9be8"),
          ("Purple", "#e8ddff", "#9b7ce2"), ("Orange", "#ffe1c4", "#f5964a"),
          ("Grey", "#eeeeee", "#9e9e9e")]
COLOR_NAMES = [c[0] for c in COLORS]


def color_info(name):
    for c in COLORS:
        if c[0] == name:
            return c
    return COLORS[0]


def swatch_icon(name, size=14):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _, paper, accent = color_info(name)
    p.setPen(QPen(QColor(accent), 1.5))
    p.setBrush(QColor(paper))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def _read_json(path, default, backup_broken=False):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        if backup_broken:                  # keep the broken file: the next save would overwrite it
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------
# data
# ----------------------------------------------------------------------
class NoteStore:
    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, NOTES_FILE)
        self.notes = []
        self.load()
        if not os.path.exists(self.path):
            self._migrate(os.path.join(base_dir, LEGACY_FILE))

    def load(self):
        data = _read_json(self.path, {}, backup_broken=True)
        raw = data.get("notes", []) if isinstance(data, dict) else []
        used = set()
        self.notes = []
        for n, it in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(it, dict):
                continue
            nid = it.get("id")
            if not isinstance(nid, int) or isinstance(nid, bool) or nid in used:
                nid = int(time.time() * 1000) + n
            used.add(nid)
            geo = it.get("geo")
            if not (isinstance(geo, list) and len(geo) == 4 and all(isinstance(v, int) for v in geo)):
                geo = None
            self.notes.append({"id": nid, "text": str(it.get("text", "")),
                               "color": it.get("color") if it.get("color") in COLOR_NAMES else "Yellow",
                               "pinned": bool(it.get("pinned", False)), "open": bool(it.get("open", False)),
                               "geo": geo, "updated": str(it.get("updated", ""))})

    def _migrate(self, legacy):
        """Bring the old single sticky note over as the first note (only once)."""
        data = _read_json(legacy, None)
        if isinstance(data, dict) and str(data.get("note", "")).strip():
            self.add(text=str(data["note"]), color="Yellow")
            try:
                os.replace(legacy, legacy + ".moved")
            except OSError:
                pass

    def save(self):
        _write_json(self.path, {"notes": self.notes})

    def get(self, nid):
        for n in self.notes:
            if n["id"] == nid:
                return n
        return None

    def add(self, text="", color="Yellow"):
        used = {n["id"] for n in self.notes}
        nid = int(time.time() * 1000)
        while nid in used:
            nid += 1
        note = {"id": nid, "text": text, "color": color if color in COLOR_NAMES else "Yellow",
                "pinned": False, "open": True, "geo": None,
                "updated": datetime.now().isoformat(timespec="seconds")}
        self.notes.append(note)
        self.save()
        return note

    def delete(self, nid):
        self.notes = [n for n in self.notes if n["id"] != nid]
        self.save()

    def search(self, query, color=None):
        """Notes that contain EVERY word of the query (any case), newest first."""
        words = [w for w in query.lower().split() if w]
        out = []
        for n in self.notes:
            if color and n["color"] != color:
                continue
            low = n["text"].lower()
            if all(w in low for w in words):
                out.append(n)
        out.sort(key=lambda n: n["updated"], reverse=True)
        return out


def first_line(text, limit=40):
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= limit else line[:limit - 1] + "\u2026"
    return "(empty note)"


def nice_time(iso):
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    if d.date() == datetime.now().date():
        return "today %s" % d.strftime("%H:%M")
    return d.strftime("%d %b %H:%M")


# ----------------------------------------------------------------------
# one note window
# ----------------------------------------------------------------------
class _DragBar(QWidget):
    """The top strip of a note: drag it to move the note, double-click it to pin."""

    def __init__(self, note_window):
        super().__init__(note_window)
        self.win = note_window
        self._grab = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._grab = event.globalPosition().toPoint() - self.win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._grab is not None:
            self.win.move(event.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, event):
        self._grab = None

    def mouseDoubleClickEvent(self, event):
        self.win.toggle_pin()


NOTE_STYLE = """
QToolButton { background: transparent; border: none; border-radius: 6px; color: #5a4a3a;
              font-size: 13px; font-weight: bold; padding: 1px 5px; }
QToolButton:hover { background: rgba(0, 0, 0, 0.08); }
QToolButton:checked { background: rgba(0, 0, 0, 0.16); }
QToolButton::menu-indicator { image: none; width: 0px; }
QPlainTextEdit { background: transparent; border: none; color: #2b2622; font-size: 14px;
                 font-family: "Segoe UI", Arial, sans-serif; selection-background-color: rgba(0,0,0,0.18); }
QLabel { color: rgba(60, 45, 30, 0.65); font-size: 10px; font-family: "Segoe UI", Arial, sans-serif; }
QScrollBar:vertical { width: 7px; background: transparent; }
QScrollBar::handle:vertical { background: rgba(0,0,0,0.18); border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class NoteWindow(QWidget):
    def __init__(self, manager, note):
        super().__init__()
        self.m = manager
        self.note = note
        self._ready = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Sticky note")
        self._apply_flags(show=False)
        self.setMinimumSize(170, 130)
        self.setStyleSheet(NOTE_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGIN + 6, MARGIN + 2, MARGIN + 4, MARGIN + 2)
        lay.setSpacing(0)
        bar = _DragBar(self)
        bar.setFixedHeight(30)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.title = QLabel()
        b_new = QToolButton()
        b_new.setText("+")
        b_new.setToolTip("New note")
        b_new.clicked.connect(lambda: self.m.new_note(near=self))
        self.b_color = QToolButton()
        self.b_color.setToolTip("Colour")
        self.b_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        cmenu = QMenu(self.b_color)
        for name in COLOR_NAMES:
            cmenu.addAction(swatch_icon(name), name).triggered.connect(
                lambda checked=False, n=name: self.set_color(n))
        self.b_color.setMenu(cmenu)
        self.b_pin = QToolButton()
        self.b_pin.setText("\U0001F4CC")
        self.b_pin.setCheckable(True)
        self.b_pin.setToolTip("Pin: keep this note on top of all windows")
        self.b_pin.clicked.connect(lambda: self.toggle_pin())
        b_close = QToolButton()
        b_close.setText("\u2715")
        b_close.setToolTip("Hide this note (it is kept; find it in Notes & search)")
        b_close.clicked.connect(self.close)
        row.addWidget(self.title, 1)
        for b in (b_new, self.b_color, self.b_pin, b_close):
            row.addWidget(b)
        lay.addWidget(bar)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Write anything...")
        self.editor.setPlainText(note["text"])
        self.editor.textChanged.connect(self._text_changed)
        lay.addWidget(self.editor, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        self.stamp = QLabel()
        foot.addWidget(self.stamp, 1)
        foot.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(foot)

        if note.get("geo"):
            x, y, w, h = note["geo"]
            self.setGeometry(x, y, max(170, w), max(130, h))
        else:
            self.resize(NOTE_W, NOTE_H)
        self._refresh_look()
        self._ready = True

    # -- appearance -------------------------------------------------------
    def _apply_flags(self, show=True):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.note["pinned"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        geo = self.geometry()
        self.setWindowFlags(flags)             # this hides the window, so show it again
        if show:
            self.setGeometry(geo)
            self.show()

    def _refresh_look(self):
        self.title.setText(first_line(self.note["text"], 22))
        self.b_color.setIcon(swatch_icon(self.note["color"], 16))
        self.b_pin.setChecked(self.note["pinned"])
        self.stamp.setText(("Pinned  \u00b7  " if self.note["pinned"] else "") +
                           ("edited " + nice_time(self.note["updated"]) if self.note["updated"] else ""))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _, paper, accent = color_info(self.note["color"])
        body = QRectF(MARGIN, MARGIN, self.width() - 2 * MARGIN, self.height() - 2 * MARGIN)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(MARGIN, 0, -1):                      # soft shadow
            p.setBrush(QColor(60, 40, 20, int(10 * (1 - (i - 1) / float(MARGIN)) ** 2) + 1))
            p.drawRoundedRect(body.adjusted(-i, -i + 2, i, i + 2), 10 + i, 10 + i)
        path = QPainterPath()
        path.addRoundedRect(body, 10, 10)
        p.setBrush(QColor(paper))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.setBrush(QColor(accent))
        p.drawRect(QRectF(body.left(), body.top(), body.width(), 5))
        p.restore()
        p.setPen(QPen(QColor(accent).darker(115), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    # -- actions ------------------------------------------------------------
    def set_color(self, name):
        self.note["color"] = name
        self._touch()
        self._refresh_look()
        self.m.list_changed()

    def toggle_pin(self):
        self.note["pinned"] = not self.note["pinned"]
        self._apply_flags(show=True)
        self._refresh_look()
        self.m.schedule_save()
        self.m.list_changed()

    def _touch(self):
        self.note["updated"] = datetime.now().isoformat(timespec="seconds")
        self.m.schedule_save()

    def _text_changed(self):
        self.note["text"] = self.editor.toPlainText()
        self._touch()
        self.title.setText(first_line(self.note["text"], 22))
        self.stamp.setText(("Pinned  \u00b7  " if self.note["pinned"] else "") + "saved")
        self.m.list_changed()

    def _geo_changed(self):
        if not self._ready:
            return
        g = self.geometry()
        self.note["geo"] = [g.x(), g.y(), g.width(), g.height()]
        self.m.schedule_save()

    def moveEvent(self, event):
        self._geo_changed()
        super().moveEvent(event)

    def resizeEvent(self, event):
        self._geo_changed()
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        if not self.note["open"]:
            self.note["open"] = True
            self.m.schedule_save()
        super().showEvent(event)

    def closeEvent(self, event):
        if not self.m.quitting:                # quitting closes every window: keep them "open"
            self.note["open"] = False
            self.m.schedule_save()
        event.accept()


# ----------------------------------------------------------------------
# the Notes & search window
# ----------------------------------------------------------------------
class NotesWindow(QDialog):
    def __init__(self, manager, style):
        super().__init__()
        self.m = manager
        self.setWindowTitle("Cat assistant - sticky notes")
        self.setMinimumSize(520, 460)
        self.setStyleSheet(style)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        title = QLabel("Sticky notes")
        title.setObjectName("h1")
        root.addWidget(title)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: type any words from a note...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.color = QComboBox()
        self.color.addItem("All colours", None)
        for name in COLOR_NAMES:
            self.color.addItem(swatch_icon(name), name, name)
        self.color.currentIndexChanged.connect(lambda _i: self.refresh())
        row.addWidget(self.search, 1)
        row.addWidget(self.color)
        root.addLayout(row)
        self.info = QLabel()
        self.info.setObjectName("hint")
        root.addWidget(self.info)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setIconSize(QSize(16, 16))
        self.list.itemDoubleClicked.connect(lambda item: self.open_selected())
        root.addWidget(self.list, 1)
        r2 = QHBoxLayout()
        for text, fn, primary in (("New note", lambda: self.m.new_note(), True),
                                  ("Open", self.open_selected, False),
                                  ("Delete", self.delete_selected, False),
                                  ("Show all", self.m.show_all, False),
                                  ("Hide all", self.m.hide_all, False)):
            b = QPushButton(text)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(lambda checked=False, f=fn: f())
            r2.addWidget(b)
        r2.addStretch()
        b_close = QPushButton("Close")
        b_close.clicked.connect(lambda checked=False: self.hide())
        r2.addWidget(b_close)
        root.addLayout(r2)
        self.refresh()

    def refresh(self):
        keep = self.selected_id()
        query = self.search.text()
        found = self.m.store.search(query, self.color.currentData())
        self.list.clear()
        for n in found:
            text = n["text"].strip()
            rest = text.partition("\n")[2]
            snippet = " ".join(rest.split())
            snippet = snippet if len(snippet) <= 110 else snippet[:109] + "\u2026"
            label = first_line(text, 60) + ("\n" + snippet if snippet else "")
            extra = []
            if n["pinned"]:
                extra.append("pinned")
            if n["updated"]:
                extra.append("edited " + nice_time(n["updated"]))
            if extra:
                label += "\n" + "   \u00b7   ".join(extra)
            item = QListWidgetItem(swatch_icon(n["color"]), label)
            item.setData(Qt.ItemDataRole.UserRole, n["id"])
            self.list.addItem(item)
            if n["id"] == keep:
                self.list.setCurrentItem(item)
        total = len(self.m.store.notes)
        if not total:
            self.info.setText("No notes yet. Click New note.")
        elif query.strip() or self.color.currentData():
            self.info.setText("%d of %d notes match." % (len(found), total))
        else:
            self.info.setText("%d note%s. Double-click a note to open it." % (total, "" if total == 1 else "s"))

    def selected_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def open_selected(self):
        nid = self.selected_id()
        if nid is not None:
            self.m.open_note(nid)

    def delete_selected(self):
        nid = self.selected_id()
        if nid is None:
            return
        note = self.m.store.get(nid)
        if note is None:
            return
        if QMessageBox.question(self, "Sticky notes", "Delete this note?\n\n%s" % first_line(note["text"], 60)) \
                == QMessageBox.StandardButton.Yes:
            self.m.delete_note(nid)


# ----------------------------------------------------------------------
# manager: Main_file.pyw only talks to this class
# ----------------------------------------------------------------------
class NotesManager:
    def __init__(self, base_dir, window_style, anchor_widget=None):
        self.store = NoteStore(base_dir)
        self.style = window_style
        self.anchor = anchor_widget            # new notes appear near this widget (the cat)
        self.windows = {}
        self.window = None
        self.quitting = False
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(SAVE_DELAY_MS)
        self.save_timer.timeout.connect(self.store.save)
        for n in self.store.notes:             # bring back the notes that were open
            if n["open"]:
                self.open_note(n["id"], activate=False)

    def count(self):
        return len(self.store.notes)

    def schedule_save(self):
        self.save_timer.start()

    def flush(self):
        """Save at once."""
        self.save_timer.stop()
        self.store.save()

    def prepare_quit(self):
        """Called just before the program quits: open notes stay open for the next start."""
        self.quitting = True
        self.flush()

    def list_changed(self):
        if self.window is not None and self.window.isVisible():
            self.window.refresh()

    def _place_new(self, win, near=None):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if near is not None:
            pos = near.pos() + QPoint(30, 30)
        else:
            base_x = screen.x() + screen.width() - NOTE_W - 40
            base_y = screen.y() + screen.height() - NOTE_H - 220
            if self.anchor is not None and self.anchor.isVisible():
                base_x = min(base_x, self.anchor.x() + self.anchor.width() // 2 - NOTE_W // 2)
            shift = 26 * (sum(1 for w in self.windows.values() if w.isVisible()) % 8)
            pos = QPoint(base_x - shift, base_y - shift)
        x = max(screen.x(), min(pos.x(), screen.x() + screen.width() - NOTE_W))
        y = max(screen.y(), min(pos.y(), screen.y() + screen.height() - NOTE_H))
        win.move(x, y)

    def new_note(self, near=None, text="", color=None):
        if color is None:
            color = near.note["color"] if near is not None else "Yellow"
        note = self.store.add(text=text, color=color)
        win = self._window(note)
        self._place_new(win, near)
        self._show(win, activate=True)
        self.list_changed()
        return note

    def _window(self, note):
        win = self.windows.get(note["id"])
        if win is None:
            win = NoteWindow(self, note)
            self.windows[note["id"]] = win
        return win

    def _show(self, win, activate=True):
        win.show()
        win.raise_()
        if activate:
            win.activateWindow()
            win.editor.setFocus()

    @staticmethod
    def _on_a_screen(win):
        """True if the top strip of the note can be seen on some screen. A note saved on a monitor
        that is now unplugged (or after a resolution change) would otherwise open where nobody sees it."""
        g = win.geometry()
        strip = QRect(g.x() + MARGIN + 10, g.y() + MARGIN, max(1, g.width() - 2 * MARGIN - 20), 30)
        for screen in QGuiApplication.screens():
            part = screen.availableGeometry().intersected(strip)
            if part.width() >= 40 and part.height() >= 12:
                return True
        return False

    def open_note(self, nid, activate=True):
        note = self.store.get(nid)
        if note is None:
            return
        win = self._window(note)
        if not note.get("geo") or not self._on_a_screen(win):
            self._place_new(win)
        self._show(win, activate)

    def delete_note(self, nid):
        win = self.windows.pop(nid, None)
        if win is not None:
            win.hide()
            win.deleteLater()
        self.store.delete(nid)
        self.list_changed()

    def show_all(self):
        if not self.store.notes:
            self.new_note()
            return
        for n in self.store.notes:
            self.open_note(n["id"], activate=False)

    def hide_all(self):
        for win in list(self.windows.values()):
            if win.isVisible():
                win.close()

    def open_manager(self):
        if self.window is None:
            self.window = NotesWindow(self, self.style)
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.search.setFocus()
