import json
import re
import threading
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal

from . import __version__
from .backend import logger

REPO = "NotHavocc/ps5-hwcon-gui"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
REQUEST_TIMEOUT_SECONDS = 10
CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000


def parse_version(text):
    """`v1.4.1` -> (1, 4, 1). None for builds without a numeric version, like PROTEST."""
    match = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def is_newer(tag, current=__version__):
    """True or False, or None when the running build has no comparable version."""
    latest, installed = parse_version(tag), parse_version(current)
    if latest is None or installed is None:
        return None
    width = max(len(latest), len(installed))
    return latest + (0,) * (width - len(latest)) > installed + (0,) * (width - len(installed))


def fetch_latest_release():
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ps5-hwcon-gui/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        release = json.load(response)
    tag = release["tag_name"]
    return {
        "tag": tag,
        "name": release.get("name") or tag,
        "changelog": (release.get("body") or "").replace("\r\n", "\n").strip(),
        "url": release.get("html_url") or RELEASES_PAGE,
        "newer": is_newer(tag),
    }


class UpdateChecker(QObject):
    """Fetches the latest GitHub release off the GUI thread and emits a bridge-style result."""

    finished = pyqtSignal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.checking = False
        self.manual = False

    def check(self, manual=False):
        self.manual = self.manual or manual
        if self.checking:
            return
        self.checking = True
        threading.Thread(target=self._run, name="ps5hw-updates", daemon=True).start()

    def _run(self):
        try:
            result = {"success": True, "data": fetch_latest_release()}
        except Exception as exc:
            logger.warning(f"Update check failed: {exc!r}")
            result = {"success": False, "error": f"Couldn't check for updates: {exc}"}
        self.finished.emit(result, self.manual)
        self.checking = False
        self.manual = False
