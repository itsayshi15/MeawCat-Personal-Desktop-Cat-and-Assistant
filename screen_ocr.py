"""
screen_ocr.py - "Read text from screen" for Peeking Cat
=========================================================
1. Tray > "Read text from screen..."  (the screen freezes and gets darker)
2. Drag a box around the text. Esc or right-click = cancel.
3. Windows' own OCR reads the text (Windows.Media.Ocr). It is offline: nothing leaves the PC.
   No extra Python package is needed: the program asks Windows PowerShell to do it.
4. A small window shows the text. Fix it if needed, then Copy it, or ask the cat to
   Explain / Summarize / Translate it, or type your own question.

Windows OCR reads the languages that are installed in Windows (Settings > Time & language >
Language). English works everywhere. Bangla is not offered by Windows OCR.
"""
import os
import subprocess
import sys
import tempfile
import threading

from PySide6.QtCore import QObject, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

OCR_TIMEOUT = 60              # seconds (the first run after a reboot can be slow)
MIN_TEXT_HEIGHT = 300         # small pictures are enlarged to at least this height: OCR reads them better

_PS_SCRIPT = r"""
param([string]$Path)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { [Console]::Error.WriteLine("NO_OCR_LANGUAGE"); exit 3 }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) { [Console]::Out.WriteLine($line.Text) }
$stream.Dispose()
"""


def _powershell_exe():
    """Windows PowerShell 5.1 (it can use Windows Runtime; PowerShell 7 cannot)."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return exe if os.path.exists(exe) else "powershell.exe"


def ocr_image_file(path):
    """Read the text in an image file. Returns (text, error message or "")."""
    if sys.platform != "win32":
        return "", "Reading text from the screen needs Windows 10 or 11."
    script = os.path.join(tempfile.gettempdir(), "peeking_cat_ocr.ps1")
    try:
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(_PS_SCRIPT)
        res = subprocess.run([_powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", script, "-Path", path],
                             capture_output=True, timeout=OCR_TIMEOUT, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        return "", "Reading the text took too long. Try a smaller area."
    except Exception as err:
        return "", "Windows PowerShell could not be started (%s)." % err
    out = res.stdout.decode("utf-8", "replace").replace("\r\n", "\n").strip()
    err = res.stderr.decode("utf-8", "replace").strip()
    if res.returncode != 0:
        if "NO_OCR_LANGUAGE" in err:
            return "", ("Windows has no OCR language installed. Add English in Settings > "
                        "Time & language > Language, then try again.")
        first = err.splitlines()[0] if err else "error %d" % res.returncode
        return "", "Windows OCR did not work: %s" % first[:200]
    return out, ""


# ----------------------------------------------------------------------
# full-screen picker: drag a box
# ----------------------------------------------------------------------
class RegionPicker(QWidget):
    """Shows a frozen copy of the screen; you drag a box over the text."""

    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.screen_ = screen
        self.shot = screen.grabWindow(0)                   # the whole screen under the mouse
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.start = None
        self.end = None
        self.finished = False

    def begin(self):
        self.showFullScreen() if sys.platform != "win32" else self.show()
        self.setGeometry(self.screen_.geometry())
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def sel_rect(self):
        if self.start is None or self.end is None:
            return QRect()
        return QRect(self.start, self.end).normalized()

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        sel = self.sel_rect()
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        if not sel.isEmpty():
            hole = QPainterPath()
            hole.addRect(QRectF(sel))
            shade = shade.subtracted(hole)
        p.fillPath(shade, QColor(10, 6, 20, 120))
        if not sel.isEmpty():
            p.setPen(QPen(QColor(255, 143, 92), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel.adjusted(0, 0, -1, -1))
        text = "Drag a box around the text you want the cat to read.   Esc = cancel"
        f = QFont("Segoe UI")
        f.setPixelSize(17)
        f.setBold(True)
        p.setFont(f)
        box = QRectF(self.width() / 2 - 330, 24, 660, 44)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 251, 245, 235))
        p.drawRoundedRect(box, 14, 14)
        p.setPen(QColor(43, 38, 34))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start is None:
            return
        self.end = event.position().toPoint()
        sel = self.sel_rect()
        if sel.width() < 8 or sel.height() < 8:
            self.start = self.end = None              # too small: try again
            self.update()
            return
        sx = self.shot.width() / float(max(1, self.width()))     # logical -> picture pixels
        sy = self.shot.height() / float(max(1, self.height()))
        crop = self.shot.copy(QRect(int(sel.x() * sx), int(sel.y() * sy),
                                    int(sel.width() * sx), int(sel.height() * sy)))
        self._finish(crop)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def _finish(self, pixmap):
        if self.finished:
            return
        self.finished = True
        self.hide()
        self.deleteLater()
        self.on_done(pixmap)


# ----------------------------------------------------------------------
# the result window
# ----------------------------------------------------------------------
class OcrWindow(QDialog):
    def __init__(self, reader, style):
        super().__init__()
        self.r = reader
        self.setWindowTitle("Cat assistant - text from the screen")
        self.setMinimumSize(560, 430)
        self.setStyleSheet(style)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        title = QLabel("Text from the screen")
        title.setObjectName("h1")
        root.addWidget(title)
        self.info = QLabel()
        self.info.setObjectName("hint")
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        self.text = QPlainTextEdit()
        self.text.setStyleSheet("QPlainTextEdit { background: white; border: 1px solid #ead3bd; "
                                "border-radius: 10px; padding: 6px; font-size: 13px; }")
        root.addWidget(self.text, 1)
        row = QHBoxLayout()
        for label, question in (("Explain", "Explain this text in simple words."),
                                ("Summarize", "Summarize this text in a few short sentences."),
                                ("To Bangla", "Translate this text into Bangla."),
                                ("To English", "Translate this text into simple English.")):
            b = QPushButton(label)
            b.clicked.connect(lambda checked=False, q=question: self.ask(q))
            row.addWidget(b)
        row.addStretch()
        b_copy = QPushButton("Copy")
        b_copy.clicked.connect(lambda checked=False: self.copy())
        row.addWidget(b_copy)
        root.addLayout(row)
        row2 = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText("Or ask your own question about this text...")
        self.question.returnPressed.connect(lambda: self.ask(self.question.text()))
        b_ask = QPushButton("Ask the cat")
        b_ask.setObjectName("primary")
        b_ask.clicked.connect(lambda checked=False: self.ask(self.question.text()))
        b_again = QPushButton("Pick again")
        b_again.clicked.connect(lambda checked=False: (self.hide(), self.r.start()))
        row2.addWidget(self.question, 1)
        row2.addWidget(b_ask)
        row2.addWidget(b_again)
        root.addLayout(row2)

    def show_result(self, text, error):
        self.text.setPlainText(text)
        if error:
            self.info.setText(error)
            self.info.setStyleSheet("color: #c0392b;")
        else:
            lines = len([ln for ln in text.splitlines() if ln.strip()])
            self.info.setText("Found %d line%s. You can fix mistakes before you ask the cat." %
                              (lines, "" if lines == 1 else "s") if lines else
                              "No text was found in that area. Try a bigger box, or zoom in first.")
            self.info.setStyleSheet("")
        self.show()
        self.raise_()
        self.activateWindow()

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.info.setText("Copied to the clipboard.")

    def ask(self, question):
        text = self.text.toPlainText().strip()
        question = question.strip()
        if not text:
            self.info.setText("There is no text to ask about.")
            return
        if not question:
            self.question.setFocus()
            return
        self.hide()
        self.question.clear()
        self.r.ask(text, question)


# ----------------------------------------------------------------------
# the manager that Main_file.pyw talks to
# ----------------------------------------------------------------------
class ScreenReader(QObject):
    _done = Signal(str, str)                  # text, error

    def __init__(self, ask_callback, window_style):
        super().__init__()
        self.ask_callback = ask_callback      # fn(text, question): opens the cat chat
        self.style = window_style
        self.window = None
        self.picker = None
        self.busy = False
        self._starting = False
        self._done.connect(self._show)

    def start(self):
        if sys.platform != "win32":
            QMessageBox.information(None, "Peeking Cat", "Reading text from the screen needs Windows 10 or 11.")
            return
        if self.busy or self.picker is not None or self._starting:
            return
        if self.window is not None:
            self.window.hide()
        # Wait a moment before the screen is "frozen": the tray menu and the text window need time
        # to disappear, or they end up inside the screenshot and cover the text you want to read.
        self._starting = True
        QTimer.singleShot(250, self._open_picker)

    def _open_picker(self):
        self._starting = False
        if self.busy or self.picker is not None:
            return
        self.picker = RegionPicker(self._picked)
        self.picker.begin()

    def _picked(self, pixmap):
        self.picker = None
        if pixmap is None or pixmap.isNull():
            return
        if pixmap.height() < MIN_TEXT_HEIGHT:            # small text: make it bigger for the OCR
            factor = min(4.0, MIN_TEXT_HEIGHT / float(max(1, pixmap.height())))
            pixmap = pixmap.scaled(int(pixmap.width() * factor), int(pixmap.height() * factor),
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        if max(pixmap.width(), pixmap.height()) > 9000:    # Windows OCR limit is 10000 pixels
            pixmap = pixmap.scaled(9000, 9000, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        path = os.path.join(tempfile.gettempdir(), "peeking_cat_ocr.png")
        if not pixmap.save(path, "PNG"):
            self._show("", "Could not save the picture for reading.")
            return
        self.busy = True
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        threading.Thread(target=self._work, args=(path,), daemon=True).start()

    def _work(self, path):
        text, err = ocr_image_file(path)
        try:
            os.remove(path)
        except OSError:
            pass
        self._done.emit(text, err)

    def _show(self, text, err):
        if self.busy:
            self.busy = False
            QApplication.restoreOverrideCursor()
        if self.window is None:
            self.window = OcrWindow(self, self.style)
        self.window.show_result(text, err)

    def ask(self, text, question):
        self.ask_callback(text, question)
