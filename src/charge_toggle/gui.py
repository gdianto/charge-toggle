"""The window: the battery level, one switch and two lines of status."""

from __future__ import annotations

import shutil
import sys
import time
from collections.abc import Callable
from importlib import resources

from PySide6.QtCore import QProcess, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from charge_toggle import control
from charge_toggle.status import Status, describe, shortfall
from charge_toggle.sysfs import AUTO, PAUSE, PowerState, read_power_state

REFRESH_MS = 2000
NOTIFY_EVERY_S = 600
AMBER = "#d97706"


def notify(summary: str, body: str) -> None:
    if shutil.which("notify-send"):
        QProcess.startDetached("notify-send", ["--app-name=Charge Toggle", summary, body])


class Switch(QAbstractButton):
    """An on/off switch in the palette's colours."""

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        track = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        role = QPalette.ColorRole.Highlight if self.isChecked() else QPalette.ColorRole.Mid
        painter.setBrush(self.palette().color(role))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        size = track.height() - 6
        x = track.right() - 3 - size if self.isChecked() else track.left() + 3
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x, track.top() + 3, size, size))


class Window(QWidget):
    def __init__(
        self,
        read: Callable[[], PowerState] = read_power_state,
        send: Callable[[str, str], None] = notify,
    ) -> None:
        super().__init__()
        self.read, self.send = read, send
        self.state = PowerState()
        self.helping_since: float | None = None  # when the battery began helping the charger
        self.notified: float | None = None
        self.process: QProcess | None = None

        self.setWindowTitle("Charge Toggle")
        self.level = QLabel()
        font = self.level.font()
        font.setPointSizeF(font.pointSizeF() * 2.6)
        font.setWeight(QFont.Weight.Light)
        self.level.setFont(font)
        self.switch = Switch()
        self.switch.clicked.connect(self.toggle)
        self.battery = QLabel()
        self.battery.setMinimumWidth(300)
        self.charger = QLabel()
        self.note = QLabel()
        for label in (self.charger, self.note):
            label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        top = QHBoxLayout()
        top.addWidget(self.level)
        top.addStretch(1)
        top.addWidget(QLabel("Charging"))
        top.addSpacing(10)
        top.addWidget(self.switch)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        layout.setContentsMargins(24, 18, 24, 22)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addSpacing(4)
        for label in (self.battery, self.charger, self.note):
            layout.addWidget(label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    def refresh(self) -> None:
        self.state = self.read()
        s = Status.of(self.state)
        now = time.monotonic()
        if not shortfall(s):
            self.helping_since = None
        elif self.helping_since is None:
            self.helping_since = now
        view = describe(s, now - (self.helping_since or now))

        self.level.setText(view.level)
        self.battery.setText(view.battery)
        self.charger.setText(view.charger)
        self.charger.setStyleSheet(f"color: {AMBER}" if view.weak else "")
        self.note.setText(view.note or "")
        self.note.setVisible(bool(view.note))

        if view.weak and (self.notified is None or now - self.notified >= NOTIFY_EVERY_S):
            self.notified = now
            self.send(
                "Charger too weak",
                f"The battery is supplying {view.shortfall:.0f} W while plugged in.",
            )

        if self.process is None:
            self.switch.setChecked(not s.paused)
            self.switch.setEnabled(s.can_pause and (s.ac or s.paused))
        self.switch.setToolTip("Connect the charger first" if s.can_pause and not s.ac else "")

    def toggle(self, on: bool) -> None:
        value = AUTO if on else PAUSE
        try:
            args = control.command(
                value, control.targets(self.state), control.elevate(interactive=False)
            )
        except control.ControlError as e:
            self.refresh()
            QMessageBox.warning(self, "Charge Toggle", str(e))
            return
        process = QProcess(self)
        process.setStandardOutputFile(QProcess.nullDevice())
        process.started.connect(
            lambda: (process.write(value.encode()), process.closeWriteChannel())
        )
        process.finished.connect(self.finished)
        process.errorOccurred.connect(self.failed)
        self.process = process
        self.switch.setEnabled(False)
        process.start(args[0], args[1:])

    def finished(self, code: int) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        err = bytes(process.readAllStandardError().data()).decode(errors="replace")
        process.deleteLater()
        self.refresh()
        if code not in (0, 126):  # 126: the password dialog was cancelled
            QMessageBox.warning(self, "Charge Toggle", control.failure(code, err))

    def failed(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self.process is None:
            return
        process, self.process = self.process, None
        process.deleteLater()
        self.refresh()
        QMessageBox.warning(self, "Charge Toggle", f"Couldn't start {process.program()}.")


def run() -> int:
    # Set before the application exists, so the desktop matches it to its menu entry.
    QApplication.setApplicationName("charge-toggle")
    QApplication.setDesktopFileName("charge-toggle")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(resources.files("charge_toggle") / "data" / "charge-toggle.svg")))
    window = Window()
    window.show()
    return app.exec()
