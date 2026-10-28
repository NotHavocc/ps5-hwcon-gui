import os
import sys

from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .bridge import BackendBridge
from . import __version__
from .common import APP_TITLE
from .pages.cpu import CpuPage
from .pages.fan import FanPage
from .pages.gpu import GpuPage
from .pages.led import LedPage
from .widgets import ACCENT, Toast, desktop_notify

ACCENT_HOVER = "#005a9e"
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_MARK = os.path.join(PACKAGE_DIR, "check.svg")
ICON_PATH = os.path.join(PACKAGE_DIR, "icon.png")

STYLESHEET = f"""
QMainWindow, #root, #pageContent, QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: #2b2b2b;
    color: #ffffff;
}}
QWidget {{
    color: #ffffff;
}}
QLabel {{
    color: #ffffff;
    background-color: transparent;
}}
QListWidget#nav {{
    background-color: #1e1e1e;
    color: #ffffff;
    border: none;
    font-size: 14px;
    outline: none;
}}
QListWidget#nav::item {{
    padding: 12px;
    border-bottom: 1px solid #3d3d3d;
}}
QListWidget#nav::item:selected {{
    background-color: {ACCENT};
    color: #ffffff;
    font-weight: bold;
}}
QListWidget#nav::item:hover:!selected {{
    background-color: #3d3d3d;
}}
QGroupBox {{
    background-color: #333333;
    color: #ffffff;
    border: 1px solid #555555;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #aaaaaa;
}}
QGroupBox QLabel, QGroupBox QCheckBox {{
    font-weight: normal;
}}
QLabel#muted {{
    color: #aaaaaa;
    font-size: 12px;
}}
QLabel#error {{
    color: #ff7b72;
    font-size: 12px;
}}
QLabel#value {{
    font-weight: bold;
}}
QLabel#value:disabled {{
    color: #777777;
}}
QLabel#danger {{
    color: #ff7b72;
    font-weight: bold;
}}
QLabel#tileValue {{
    font-weight: bold;
}}
QLabel#tileValue[level="warm"] {{
    color: #f0b44c;
}}
QLabel#tileValue[level="hot"] {{
    color: #ff6b5f;
}}
QSlider::groove:horizontal {{
    border: 1px solid #555555;
    height: 4px;
    background: #444444;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    border: 1px solid {ACCENT_HOVER};
    width: 12px;
    margin: -4px 0;
    border-radius: 2px;
}}
QSlider::handle:horizontal:disabled {{
    background: #666666;
    border-color: #555555;
}}
QCheckBox {{
    color: #ffffff;
    background-color: transparent;
    spacing: 5px;
}}
QCheckBox:disabled {{
    color: #777777;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #444444;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT_HOVER};
    image: url("{CHECK_MARK}");
}}
QCheckBox::indicator:disabled {{
    background-color: #3a3a3a;
    border-color: #4a4a4a;
}}
QCheckBox::indicator:checked:disabled {{
    background-color: #2d5a80;
}}
QPushButton {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton:disabled {{
    background-color: #444444;
    color: #888888;
}}
QPushButton#cancelBtn, QPushButton#choice {{
    background-color: #555555;
}}
QPushButton#cancelBtn:hover, QPushButton#choice:hover {{
    background-color: #666666;
}}
QPushButton#choice {{
    padding: 0;
}}
QPushButton#choice[selected="true"] {{
    background-color: {ACCENT};
}}
QPushButton#choice[selected="true"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#choice:disabled {{
    background-color: #444444;
}}
QPushButton#choice[selected="true"]:disabled {{
    background-color: #2d5a80;
}}
QPushButton#small {{
    padding: 5px 14px;
}}
QLabel#choiceTitle {{
    font-weight: bold;
}}
QLabel#choiceSub {{
    color: #dddddd;
    font-size: 11px;
}}
QLabel#choiceTitle:disabled, QLabel#choiceSub:disabled {{
    color: #888888;
}}
#presetRow {{
    border-bottom: 1px solid #3d3d3d;
}}
QToolButton#reset {{
    background: transparent;
    border: none;
    color: #aaaaaa;
    font-size: 14px;
    padding: 0 2px;
}}
QToolButton#reset:hover {{
    color: {ACCENT};
}}
QLineEdit {{
    background-color: #444444;
    color: #ffffff;
    border: 1px solid #555555;
    padding: 4px;
    border-radius: 3px;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
#banner {{
    background-color: #4a3a1a;
    border-bottom: 1px solid #6b5420;
}}
#banner QLabel {{
    color: #ffd98a;
}}
#toast {{
    background-color: #333333;
    border: 1px solid #555555;
    border-left: 4px solid {ACCENT};
    border-radius: 4px;
}}
#toast[critical="true"] {{
    border-left-color: #ff6b5f;
}}
QScrollBar:vertical {{
    background: #2b2b2b;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #555555;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


_icon = None


def app_icon():
    global _icon
    if _icon is None:
        _icon = QIcon(ICON_PATH)
    return _icon


class AboutPage(QWidget):
    LINKS = (
        ("My Website", "https://nothavoc.is-a.dev"),
        ("Check For Updates", "https://github.com/NotHavocc/ps5-hwcon-gui/releases/latest"),
    )

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setPixmap(
            QPixmap(ICON_PATH).scaled(
                112, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("margin-bottom: 15px;")
        layout.addWidget(icon)
        title = QLabel(APP_TITLE)
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {ACCENT}; margin-bottom: 5px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        version = QLabel(f"Version {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(version)
        desc = QLabel(
            "Fan curve or target, temperatures, CPU and GPU governors and clocks, "
            "and indicator LED presets for PS5 Linux."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #cccccc; margin-top: 20px; font-size: 14px;")
        layout.addWidget(desc)
        self.environment = QLabel()
        self.environment.setWordWrap(True)
        self.environment.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.environment.setStyleSheet("color: #aaaaaa; margin-top: 12px;")
        layout.addWidget(self.environment)
        for text, url in self.LINKS:
            link = QLabel(f'<a href="{url}" style="color: {ACCENT}; text-decoration: none;">{text}</a>')
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setStyleSheet("margin-top: 8px; font-size: 14px;")
            layout.addWidget(link)

    def set_environment(self, data):
        self.environment.setText(
            f"Running as {'root' if data['root'] else 'a normal user'} - "
            f"settings in {data['settings_path']}"
        )


class MainWindow(QMainWindow):
    PAGES = (("Fan", FanPage), ("CPU", CpuPage), ("GPU", GpuPage), ("LED", LedPage))
    ABOUT_ROW = 0
    DEFAULT_ROW = 1

    def __init__(self, bridge, start_hidden=False):
        super().__init__()
        self.bridge = bridge
        self.quitting = False
        self.settings = QSettings("ps5-hwcon", "ps5-hwcon-gui")
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(760, 640)
        self.setMinimumSize(QSize(600, 450))

        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.banner = QWidget()
        self.banner.setObjectName("banner")
        self.banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 6, 14, 6)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label)
        self.banner.hide()
        outer.addWidget(self.banner)

        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        outer.addLayout(main, 1)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(160)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main.addWidget(self.nav)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(20, 10, 20, 16)
        buttons.setSpacing(10)
        buttons.addStretch(1)
        hide_button = QPushButton("Hide to Tray")
        hide_button.setObjectName("cancelBtn")
        hide_button.clicked.connect(self.close)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.quit)
        buttons.addWidget(hide_button)
        buttons.addWidget(quit_button)
        right.addLayout(buttons)
        main.addLayout(right, 1)
        self.setCentralWidget(root)

        self.toast = Toast(root, above=self.banner)
        self.about = AboutPage()
        self.stack.addWidget(self.about)
        QListWidgetItem("About", self.nav)
        self.pages = []
        for label, page_class in self.PAGES:
            page = page_class(bridge, self.notify)
            self.pages.append(page)
            self.stack.addWidget(page)
            QListWidgetItem(label, self.nav)
        self.nav.currentRowChanged.connect(self._select_page)
        last = self.settings.value("last_tab", self.DEFAULT_ROW, type=int)
        self.nav.setCurrentRow(last if 0 <= last < self.nav.count() else self.DEFAULT_ROW)

        self._setup_tray()
        hide_button.setVisible(self.tray is not None)
        self.bridge.ready.connect(self._backend_ready)
        if not start_hidden:
            self.show()

    def _page_at(self, row):
        return self.pages[row - 1] if row > self.ABOUT_ROW else None

    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_TITLE)
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        # macOS testing slop (bcs im developing GUI on mac)
        if sys.platform != "darwin":
            self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger or sys.platform == "darwin"
            else None
        )
        self._tray_menu = menu
        self.tray.show()

    def _backend_ready(self):
        self.bridge.call("get_environment", callback=self._environment_loaded)
        self._select_page(self.nav.currentRow())

    def _environment_loaded(self, result):
        if not result["success"]:
            return
        notes = []
        if not result["data"]["root"]:
            notes.append("Not running as root, so changes will fail with permission errors.")
        self.about.set_environment(result["data"])
        if result["data"]["missing"]:
            notes.append(
                "Missing kernel interfaces: "
                + ", ".join(result["data"]["missing"])
                + ". Is the ps5-linux-patches kernel running?"
            )
        self.banner_label.setText("  ".join(notes))
        self.banner.setVisible(bool(notes))

    def _select_page(self, index):
        if index < 0:
            return
        current = self._page_at(index)
        for page in self.pages:
            if page is not current:
                page.deactivate()
        self.stack.setCurrentIndex(index)
        self.settings.setValue("last_tab", index)
        if current and self.bridge.is_ready and self.isVisible():
            current.activate()

    def notify(self, result, quiet=False):
        if result["success"]:
            if not quiet:
                self.toast.show_message(result["message"])
        else:
            self.toast.show_message(result["error"], critical=True)
            if not self.isVisible() and self.tray is not None:
                self._tray_message(result["error"], warning=True)

    def _tray_message(self, text, warning=False):
        if sys.platform.startswith("linux"):
            desktop_notify(APP_TITLE, text, warning)
        else:
            icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
            self.tray.showMessage(APP_TITLE, text, icon)

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        current = self._page_at(self.nav.currentRow())
        if current and self.bridge.is_ready:
            current.activate()

    def hideEvent(self, event):
        super().hideEvent(event)
        if not self.isMinimized():
            for page in self.pages:
                page.deactivate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event):
        if self.quitting or self.tray is None:
            event.accept()
            QApplication.instance().quit()
            return
        event.ignore()
        self.hide()
        if not self.settings.value("tray_hint_shown", False, type=bool):
            self.settings.setValue("tray_hint_shown", True)
            self._tray_message(
                "Still running in the tray, so Thermal Guard and LED loops keep working. "
                "Use Quit to exit."
            )

    def quit(self):
        self.quitting = True
        self.close()
        QApplication.instance().quit()


def run_gui(argv, start_hidden=False):
    app = QApplication(argv)
    app.setApplicationName("ps5-hwcon-gui")
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    bridge = BackendBridge()
    window = MainWindow(bridge, start_hidden=start_hidden and QSystemTrayIcon.isSystemTrayAvailable())
    bridge.start()
    app.aboutToQuit.connect(bridge.stop)
    return app.exec()
