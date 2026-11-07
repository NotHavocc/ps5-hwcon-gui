import os
import select
import subprocess
import sys

from PyQt6.QtCore import QEventLoop, QObject, QSocketNotifier, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .backend import invoking_user, logger, user_process_options, user_session_env
from .common import APP_TITLE
from .widgets import desktop_notify

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PACKAGE_DIR, "icon.png")
TRAY_WAIT_MS = 15000
TRAY_POLL_MS = 500
HELPER_FLAG = "--tray-helper"
HELPER_START_S = 15


def wait_for_tray(wait_ms):
    waited = 0
    while not QSystemTrayIcon.isSystemTrayAvailable() and waited < wait_ms:
        loop = QEventLoop()
        QTimer.singleShot(TRAY_POLL_MS, loop.quit)
        loop.exec()
        waited += TRAY_POLL_MS
    if waited:
        logger.info(f"Waited {waited / 1000:g} s for the system tray")
    return QSystemTrayIcon.isSystemTrayAvailable()


class LocalTray(QObject):
    show_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(icon, self)
        self.icon.setToolTip(APP_TITLE)
        self.menu = QMenu()
        show_action = QAction("Show", self.menu)
        show_action.triggered.connect(self.show_requested)
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.quit_requested)
        self.menu.addAction(show_action)
        self.menu.addSeparator()
        self.menu.addAction(quit_action)
        # macOS testing slop (bcs im developing GUI on mac)
        if sys.platform != "darwin":
            self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.icon.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger or sys.platform == "darwin":
            self.show_requested.emit()

    def show_message(self, text, warning=False):
        if sys.platform.startswith("linux"):
            desktop_notify(APP_TITLE, text, warning)
        else:
            icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
            self.icon.showMessage(APP_TITLE, text, icon)

    def stop(self):
        self.icon.hide()


class HelperTray(QObject):
    show_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, process, parent=None):
        super().__init__(parent)
        self.process = process
        self._buffer = b""
        self.notifier = QSocketNotifier(process.stdout.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._read)

    def _read(self):
        try:
            data = os.read(self.process.stdout.fileno(), 4096)
        except OSError:
            data = b""
        if not data:
            self.notifier.setEnabled(False)
            logger.warning("The tray helper exited, so the tray icon is gone")
            return
        self._buffer += data
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            if line == b"show":
                self.show_requested.emit()
            elif line == b"quit":
                self.quit_requested.emit()

    def show_message(self, text, warning=False):
        text = " ".join(text.split())
        try:
            self.process.stdin.write(f"{'warn' if warning else 'info'}\t{text}\n".encode())
        except OSError:
            pass

    def stop(self):
        self.notifier.setEnabled(False)
        try:
            self.process.stdin.close()
            self.process.wait(timeout=2)
        except OSError:
            pass
        except subprocess.TimeoutExpired:
            self.process.kill()


def _helper_command(wait_ms):
    if getattr(sys, "frozen", False):
        return [sys.executable, HELPER_FLAG, str(wait_ms)]
    return [sys.executable, "-m", "ps5hwcon", HELPER_FLAG, str(wait_ms)]


def _start_helper(user, options, wait_ms):
    env = user_session_env(user)
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = os.path.dirname(PACKAGE_DIR)
    try:
        process = subprocess.Popen(
            _helper_command(wait_ms),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
            env=env,
            **options,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning(f"Couldn't start the tray helper: {error}")
        return None
    ready, _, _ = select.select([process.stdout], [], [], wait_ms / 1000 + HELPER_START_S)
    status = process.stdout.readline().strip() if ready else b""
    if status == b"ready":
        return HelperTray(process)
    logger.info(
        "No system tray found" if status == b"unavailable" else "The tray helper didn't start"
    )
    process.kill()
    process.wait()
    return None


def create_tray(icon, wait_ms=0):
    user = invoking_user()
    options = user_process_options(user) if sys.platform.startswith("linux") else {}
    if options:
        return _start_helper(user, options, wait_ms)
    return LocalTray(icon) if wait_for_tray(wait_ms) else None


def run_helper(wait_ms):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ps5-hwcon-gui")
    app.setApplicationDisplayName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)

    def send(word):
        try:
            os.write(sys.stdout.fileno(), f"{word}\n".encode())
        except OSError:
            app.quit()

    if not wait_for_tray(wait_ms):
        send("unavailable")
        return 1
    tray = LocalTray(QIcon(ICON_PATH))
    tray.show_requested.connect(lambda: send("show"))
    tray.quit_requested.connect(lambda: send("quit"))

    buffer = b""

    def receive():
        nonlocal buffer
        try:
            data = os.read(sys.stdin.fileno(), 4096)
        except OSError:
            data = b""
        if not data:
            app.quit()
            return
        buffer += data
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            kind, _, text = line.decode(errors="replace").partition("\t")
            if text:
                tray.show_message(text, warning=kind == "warn")

    notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(receive)
    send("ready")
    status = app.exec()
    tray.stop()
    return status
