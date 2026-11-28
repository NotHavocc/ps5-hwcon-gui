import os
import re
import subprocess
import sys

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .backend import _command_env, invoking_user, logger, user_process_options, user_session_env
from .bridge import BackendBridge
from . import __version__
from .common import APP_TITLE
from .pages.cpu import CpuPage
from .pages.dashboard import DashboardPage
from .pages.display import DisplayPage
from .pages.fan import FanPage
from .pages.gpu import GpuPage
from .pages.group import PageGroup
from .pages.led import LedPage
from .pages.memory import MemoryPage
from .pages.performance import PerformancePage
from .telemetry import Telemetry
from .tray import ICON_PATH, TRAY_WAIT_MS, create_tray
from .updates import CHECK_INTERVAL_MS, UpdateChecker
from .widgets import (
    ACCENT_COLORS,
    ButtonGrid,
    ChoiceButton,
    ColorSwatch,
    Toast,
    ToggleRow,
    accent_colors,
    current_accent,
    restyle,
    set_current_accent,
)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_MARK = os.path.join(PACKAGE_DIR, "check.svg")
AUTOSTART_ABOUT = "Runs Thermal Guard and LED loops in the background."
AUTO_UPDATES_ABOUT = "Checks GitHub at startup and once a day."
WARM_REBOOT_WARNING = (
    "Restart Linux without going through the PS5 OS and the loader?\n\n"
    "Other apps close without saving. cmdline.txt changes apply, but a VRAM change needs a full "
    "start with the loader. The warm reboot is experimental: if the console doesn't come back, "
    "power it off and start Linux the usual way."
)
URL_OPENERS = (("xdg-open",), ("gio", "open"))
KDE_OPENERS = (("kde-open",), ("kde-open5",))

def stylesheet(colors):
    return f"""
QMainWindow, QDialog, #root, #pageContent, QScrollArea, QScrollArea > QWidget > QWidget {{
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
QMenu {{
    background-color: #333333;
    border: 1px solid #555555;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {colors.accent};
}}
QMenu::item:disabled {{
    color: #777777;
}}
QMenu::separator {{
    height: 1px;
    background: #555555;
    margin: 4px 8px;
}}
QToolTip {{
    background-color: #333333;
    color: #ffffff;
    border: 1px solid #555555;
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
    background-color: {colors.accent};
    color: #ffffff;
    font-weight: bold;
}}
QListWidget#nav::item:hover:!selected {{
    background-color: #3d3d3d;
}}
QWidget#navPanel {{
    background-color: #1e1e1e;
}}
QLabel#consoleBadge {{
    color: #aaaaaa;
    padding: 10px 12px;
    font-size: 12px;
}}
QLabel#consoleBadge[pro="true"] {{
    color: {colors.accent};
    font-weight: bold;
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
    background: {colors.accent};
    border: 1px solid {colors.hover};
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
    border-color: {colors.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {colors.accent};
    border-color: {colors.hover};
    image: url("{CHECK_MARK}");
}}
QCheckBox::indicator:disabled {{
    background-color: #3a3a3a;
    border-color: #4a4a4a;
}}
QCheckBox::indicator:checked:disabled {{
    background-color: {colors.muted};
}}
QPushButton {{
    background-color: {colors.accent};
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {colors.hover};
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
    background-color: {colors.accent};
}}
QPushButton#choice[selected="true"]:hover {{
    background-color: {colors.hover};
}}
QPushButton#choice:disabled {{
    background-color: #444444;
}}
QPushButton#choice[selected="true"]:disabled {{
    background-color: {colors.muted};
}}
QPushButton#swatch {{
    padding: 0;
    border: 2px solid transparent;
    border-radius: 4px;
}}
QPushButton#swatch:hover {{
    border-color: #888888;
}}
QPushButton#swatch[selected="true"] {{
    border-color: #ffffff;
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
    color: {colors.accent};
}}
QLineEdit {{
    background-color: #444444;
    color: #ffffff;
    border: 1px solid #555555;
    padding: 4px;
    border-radius: 3px;
}}
QLineEdit:focus {{
    border-color: {colors.accent};
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
    border-left: 4px solid {colors.accent};
    border-radius: 4px;
}}
#toast[critical="true"] {{
    border-left-color: #ff6b5f;
}}
QTextBrowser {{
    background-color: #333333;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px;
}}
QProgressBar#load {{
    background-color: #444444;
    border: none;
    border-radius: 3px;
}}
QProgressBar#load::chunk {{
    background-color: {colors.accent};
    border-radius: 3px;
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


def apply_accent(colors):
    set_current_accent(colors)
    app = QApplication.instance()
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor(colors.accent))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(colors))
    for widget in app.allWidgets():
        widget.update()


_icon = None


def app_icon():
    global _icon
    if _icon is None:
        _icon = QIcon(ICON_PATH)
    return _icon


def open_url(url):
    if not sys.platform.startswith("linux"):
        QDesktopServices.openUrl(QUrl(url))
        return
    user = invoking_user()
    options = user_process_options(user)
    options["env"] = user_session_env(user) if options else _command_env()
    openers = URL_OPENERS
    if "KDE" in options["env"].get("XDG_CURRENT_DESKTOP", "").upper().split(":"):
        openers = KDE_OPENERS + URL_OPENERS
    for opener in openers:
        try:
            subprocess.Popen(
                [*opener, url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                **options,
            )
            return
        except OSError as exc:
            logger.debug(f"{opener[0]} couldn't open {url}: {exc}")
    logger.warning(f"No URL opener worked for {url}, falling back to Qt")
    QDesktopServices.openUrl(QUrl(url))


CONSOLE_CHOICES = (("auto", "Auto"), ("pro", "PS5 Pro"), ("base", "PS5 / Slim"))
CONSOLE_NAMES = {"pro": "PS5 Pro", "base": "PS5 or PS5 Slim"}


def console_summary(console):
    if console is None:
        return "Detecting the console model…"
    detected = console["detected"]
    if detected is None:
        found = "The console model couldn't be detected (no AMD GPU in sysfs)"
    else:
        found = f"Detected {CONSOLE_NAMES[detected]} from the {console['source']}"
    if console["override"] != "auto":
        found += f", overridden to {CONSOLE_NAMES[console['override']]}"
    return found


class UpdateDialog(QDialog):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        newer = release["newer"]
        self.setWindowTitle("Update Available" if newer else "Latest Release")
        self.resize(540, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        if newer:
            heading = f"{release['name']} is available (you have {__version__})"
        else:
            heading = f"The latest release is {release['name']} (you have {__version__})"
        title = QLabel(heading)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)
        changelog = QTextBrowser()
        changelog.setOpenLinks(False)
        changelog.anchorClicked.connect(lambda url: open_url(url.toString()))
        text = re.sub(r"(?<![<(])(https?://\S+)", r"<\1>", release["changelog"])
        changelog.setMarkdown(text or "No changelog was published for this release.")
        layout.addWidget(changelog, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setObjectName("cancelBtn")
        close_button.clicked.connect(self.reject)
        open_button = QPushButton("Open Release Page")
        open_button.clicked.connect(lambda: (open_url(release["url"]), self.accept()))
        open_button.setDefault(True)
        buttons.addWidget(close_button)
        buttons.addWidget(open_button)
        layout.addLayout(buttons)


class AboutPage(QWidget):
    LINKS = (("My Website", "https://nothavoc.is-a.dev"),)

    def __init__(self, bridge, notify, on_console, updates, settings):
        super().__init__()
        self.bridge = bridge
        self.notify = notify
        self.on_console = on_console
        self.updates = updates
        self.settings = settings
        self.release = None
        self.console = None
        self.console_saving = None
        self.autostart = None
        self.saving_autostart = False
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setPixmap(
            QPixmap(ICON_PATH).scaled(
                80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        self.title = QLabel(APP_TITLE)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.version = QLabel(f"Version {__version__}")
        self.version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self.version)
        desc = QLabel("Fan, CPU, GPU, memory and LED control for PS5 Linux")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #cccccc; margin-top: 10px;")
        layout.addWidget(desc)
        actions = QHBoxLayout()
        actions.setSpacing(16)
        actions.addStretch(1)
        self.update_button = QPushButton("Check for Updates")
        self.update_button.setObjectName("small")
        self.update_button.clicked.connect(self.check_updates)
        actions.addWidget(self.update_button)
        self.links = []
        for text, url in self.LINKS:
            link = QLabel()
            link.setTextFormat(Qt.TextFormat.RichText)
            link.linkActivated.connect(open_url)
            actions.addWidget(link)
            self.links.append((link, text, url))
        actions.addStretch(1)
        layout.addSpacing(10)
        layout.addLayout(actions)
        model_title = QLabel("Console Model")
        model_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        model_title.setStyleSheet("margin-top: 16px; font-weight: bold;")
        layout.addWidget(model_title)
        self.console_buttons = {}
        for model, label in CONSOLE_CHOICES:
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, m=model: self.save_console(m))
            self.console_buttons[model] = button
        grid = ButtonGrid(columns=len(CONSOLE_CHOICES))
        grid.set_buttons(self.console_buttons.values())
        grid.setFixedWidth(420)
        layout.addWidget(grid, 0, Qt.AlignmentFlag.AlignHCenter)
        self.console_note = QLabel()
        self.console_note.setObjectName("muted")
        self.console_note.setWordWrap(True)
        self.console_note.setFixedWidth(420)
        self.console_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.console_note, 0, Qt.AlignmentFlag.AlignHCenter)
        self.render_console()
        accent_title = QLabel("Accent Color")
        accent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent_title.setStyleSheet("margin-top: 16px; font-weight: bold;")
        layout.addWidget(accent_title)
        self.accent_buttons = {}
        for colors in ACCENT_COLORS:
            button = ColorSwatch(colors)
            button.clicked.connect(lambda _=False, c=colors: self.save_accent(c))
            self.accent_buttons[colors.key] = button
        accent_grid = ButtonGrid(columns=len(ACCENT_COLORS))
        accent_grid.set_buttons(self.accent_buttons.values())
        accent_grid.setFixedWidth(420)
        layout.addWidget(accent_grid, 0, Qt.AlignmentFlag.AlignHCenter)
        self.render_accent()
        self.autostart_toggle = ToggleRow("Start in Tray at Login", AUTOSTART_ABOUT, hint="Opens hidden in the tray at login.")
        self.autostart_toggle.setFixedWidth(420)
        self.autostart_toggle.setContentsMargins(0, 16, 0, 0)
        self.autostart_toggle.toggled.connect(self.save_autostart)
        self.autostart_toggle.hide()
        layout.addWidget(self.autostart_toggle, 0, Qt.AlignmentFlag.AlignHCenter)
        self.auto_update_toggle = ToggleRow(
            "Check for Updates Automatically", AUTO_UPDATES_ABOUT, hint="Checks GitHub once a day."
        )
        self.auto_update_toggle.setFixedWidth(420)
        self.auto_update_toggle.setContentsMargins(0, 8, 0, 0)
        self.auto_update_toggle.set_checked(self.auto_updates_enabled())
        self.auto_update_toggle.toggled.connect(lambda checked: self.settings.setValue("check_updates", checked))
        layout.addWidget(self.auto_update_toggle, 0, Qt.AlignmentFlag.AlignHCenter)

    def save_accent(self, colors):
        if colors == current_accent():
            return
        self.settings.setValue("accent", colors.key)
        apply_accent(colors)
        self.render_accent()

    def render_accent(self):
        colors = current_accent()
        self.title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {colors.accent}; margin-top: 8px;"
        )
        for link, text, url in self.links:
            link.setText(f'<a href="{url}" style="color: {colors.accent}; text-decoration: none;">{text}</a>')
        for key, button in self.accent_buttons.items():
            button.set_selected(key == colors.key)

    def auto_updates_enabled(self):
        return self.settings.value("check_updates", True, type=bool)

    def check_updates(self):
        if self.release is not None and self.release["newer"]:
            self.show_release()
            return
        self.update_button.setEnabled(False)
        self.update_button.setText("Checking…")
        self.updates.check(manual=True)

    def show_release(self):
        UpdateDialog(self.release, self.window()).exec()

    def set_release(self, result, manual):
        self.update_button.setEnabled(True)
        if not result["success"]:
            self.update_button.setText("Check for Updates")
            if manual:
                self.notify(result)
            return
        self.release = result["data"]
        name = self.release["name"]
        newer = self.release["newer"]
        self.update_button.setText(f"View {name} Changelog" if newer else "Check for Updates")
        if not manual:
            return
        if newer is False:
            self.notify({"success": True, "message": f"You're on the latest version ({__version__})."})
        else:
            self.show_release()

    def set_console(self, console):
        self.console = console
        self.render_console()

    def save_console(self, model):
        if self.console is None or model == self.console["override"]:
            return
        self.console_saving = model
        self.render_console()

        def done(result):
            self.notify(result)
            self.console_saving = None
            if result["success"]:
                self.on_console(result["data"])
            else:
                self.render_console()

        self.bridge.call("set_console_model", model, callback=done)

    def render_console(self):
        console = self.console
        for model, button in self.console_buttons.items():
            button.setEnabled(console is not None and self.console_saving is None)
            button.set_selected(console is not None and console["override"] == model)
            button.set_busy(self.console_saving == model)
        self.console_note.setText(console_summary(console))

    def load_autostart(self):
        self.bridge.call("get_autostart", callback=self._autostart_loaded)

    def _autostart_loaded(self, result):
        if result["success"]:
            self.autostart = result["data"]
        self.saving_autostart = False
        self.render_autostart()

    def save_autostart(self, checked):
        self.saving_autostart = True
        self.render_autostart()

        def done(result):
            self.notify(result)
            self._autostart_loaded(result)

        self.bridge.call("set_autostart", checked, callback=done)

    def render_autostart(self):
        state = self.autostart
        if state is None:
            return
        self.autostart_toggle.show()
        self.autostart_toggle.set_checked(state["enabled"])
        self.autostart_toggle.setEnabled(
            (state["available"] or state["enabled"]) and not self.saving_autostart
        )
        if not state["available"]:
            self.autostart_toggle.set_note(state["reason"])
        elif not state["passwordless"]:
            self.autostart_toggle.set_note("Asks for your password at login (no --passwordless).")
        else:
            self.autostart_toggle.set_note(None)

    def set_environment(self, data):
        self.version.setToolTip(
            f"Running as {'root' if data['root'] else 'a normal user'}. "
            f"Settings in {data['settings_path']}"
        )


class MainWindow(QMainWindow):
    PAGES = (
        ("Dashboard", (("Now", DashboardPage), ("History", PerformancePage))),
        ("Fan", FanPage),
        ("CPU & GPU", (("CPU", CpuPage), ("GPU", GpuPage))),
        ("Memory", MemoryPage),
        ("Display", DisplayPage),
        ("LED", LedPage),
    )

    def __init__(self, bridge, tray=None, start_hidden=False):
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

        nav_panel = QWidget()
        nav_panel.setObjectName("navPanel")
        nav_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        nav_panel.setFixedWidth(160)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_layout.addWidget(self.nav, 1)
        self.console_badge = QLabel()
        self.console_badge.setObjectName("consoleBadge")
        self.console_badge.setWordWrap(True)
        nav_layout.addWidget(self.console_badge)
        main.addWidget(nav_panel)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(20, 10, 20, 16)
        buttons.setSpacing(10)
        self.warm_reboot_button = QPushButton("Warm Reboot")
        self.warm_reboot_button.setObjectName("cancelBtn")
        self.warm_reboot_button.setToolTip("Restarts Linux without the PS5 OS or the loader.")
        self.warm_reboot_button.clicked.connect(self.warm_reboot)
        self.warm_reboot_button.hide()
        buttons.addWidget(self.warm_reboot_button)
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
        self.updates = UpdateChecker(self)
        self.updates.finished.connect(self._updates_checked)
        self.about = AboutPage(bridge, self.notify, self._console_loaded, self.updates, self.settings)
        self.telemetry = Telemetry(bridge, self)
        self.pages = []
        for label, spec in self.PAGES:
            if isinstance(spec, tuple):
                page = PageGroup(label, [(name, self._make_page(cls)) for name, cls in spec])
            else:
                page = self._make_page(spec)
            self.pages.append(page)
            self.stack.addWidget(page)
            QListWidgetItem(label, self.nav)
        self.stack.addWidget(self.about)
        QListWidgetItem("About", self.nav)
        self.nav.currentRowChanged.connect(self._select_page)
        last = self.settings.value("last_page", "", type=str)
        labels = [self.nav.item(row).text() for row in range(self.nav.count())]
        self.nav.setCurrentRow(labels.index(last) if last in labels else 0)

        self._setup_tray(tray)
        hide_button.setVisible(self.tray is not None)
        self.bridge.ready.connect(self._backend_ready)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(CHECK_INTERVAL_MS)
        self.update_timer.timeout.connect(self._auto_check_updates)
        self.update_timer.start()
        self._auto_check_updates()
        if not start_hidden:
            self.show()

    def _make_page(self, page_class):
        if page_class.needs_telemetry:
            return page_class(self.bridge, self.notify, self.telemetry)
        return page_class(self.bridge, self.notify)

    def _page_at(self, row):
        return self.pages[row] if 0 <= row < len(self.pages) else None

    def _setup_tray(self, tray):
        self.tray = tray
        if tray is not None:
            tray.show_requested.connect(self.show_window)
            tray.quit_requested.connect(self.quit)

    def _backend_ready(self):
        self.telemetry.start()
        self.bridge.call("get_warm_reboot", callback=self._warm_reboot_loaded)
        self.bridge.call("get_environment", callback=self._environment_loaded)
        self.bridge.call(
            "get_console",
            callback=lambda r: self._console_loaded(r["data"]) if r["success"] else self.notify(r),
        )
        if self.tray is not None:
            self.about.load_autostart()
        self._select_page(self.nav.currentRow())

    def _auto_check_updates(self):
        if self.about.auto_updates_enabled():
            self.updates.check()

    def _updates_checked(self, result, manual):
        self.about.set_release(result, manual)
        if manual or not result["success"] or not result["data"]["newer"]:
            return
        tag = result["data"]["tag"]
        if self.settings.value("update_notified", "") == tag:
            return
        self.settings.setValue("update_notified", tag)
        message = f"{result['data']['name']} is available. See About for the changelog."
        self.toast.show_message(message)
        if not self.isVisible() and self.tray is not None:
            self._tray_message(message)

    def _warm_reboot_loaded(self, result):
        available = result["success"] and result["data"]["available"]
        self.warm_reboot_button.setVisible(available)

    def warm_reboot(self):
        answer = QMessageBox.question(
            self, "Warm Reboot", WARM_REBOOT_WARNING,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.warm_reboot_button.setEnabled(False)
        self.warm_reboot_button.setText("Restarting…")

        def done(result):
            self.notify(result)
            if not result["success"]:
                self.warm_reboot_button.setEnabled(True)
                self.warm_reboot_button.setText("Warm Reboot")

        self.bridge.call("warm_reboot", callback=done)

    def _console_loaded(self, console):
        model = console["model"]
        self.console_badge.setText(CONSOLE_NAMES.get(model, "Unknown model"))
        self.console_badge.setToolTip(console_summary(console))
        self.console_badge.setProperty("pro", console["pro"])
        restyle(self.console_badge)
        self.setWindowTitle(f"{APP_TITLE} - PS5 Pro" if console["pro"] else APP_TITLE)
        self.about.set_console(console)
        for page in self.pages:
            page.set_console(console)

    def _environment_loaded(self, result):
        if not result["success"]:
            return
        notes = []
        if not result["data"]["root"]:
            notes.append("Not running as root, so changes will fail with permission errors")
        self.about.set_environment(result["data"])
        if result["data"]["missing"]:
            notes.append(
                "Missing kernel interfaces: "
                + ", ".join(result["data"]["missing"])
                + " (is the ps5-linux-patches kernel running?)"
            )
        self.banner_label.setText("\n".join(notes))
        self.banner.setVisible(bool(notes))

    def _select_page(self, index):
        if index < 0:
            return
        current = self._page_at(index)
        for page in self.pages:
            if page is not current:
                page.deactivate()
        self.stack.setCurrentIndex(index)
        self.settings.setValue("last_page", self.nav.item(index).text())
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
        self.tray.show_message(text, warning)

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
                "Still running in the tray."
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
    apply_accent(accent_colors(QSettings("ps5-hwcon", "ps5-hwcon-gui").value("accent", "", type=str)))
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    tray = create_tray(app_icon(), wait_ms=TRAY_WAIT_MS if start_hidden else 0)
    bridge = BackendBridge()
    window = MainWindow(bridge, tray, start_hidden=start_hidden and tray is not None)
    bridge.start()
    app.aboutToQuit.connect(bridge.stop)
    if tray is not None:
        app.aboutToQuit.connect(tray.stop)
    return app.exec()
