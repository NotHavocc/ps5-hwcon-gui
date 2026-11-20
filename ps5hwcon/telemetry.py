import csv
import os
import time
from collections import deque

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .backend import invoking_user
from .common import STATUS_POLL_MS, pwm_to_percent

HISTORY_SECONDS = 10 * 60
METRIC_NAMES = {
    "cpu_mhz": "CPU Clock (MHz)",
    "gpu_mhz": "GPU Clock (MHz)",
    "cpu_load": "CPU Load (%)",
    "gpu_busy": "GPU Busy (%)",
    "fan": "Fan Speed (%)",
    "ram": "RAM Used (%)",
    "swap": "Swap Used (%)",
    "vram": "VRAM Used (%)",
}


def used_bytes(total, free):
    return total - free if total and free is not None else None


def _percent(used, total):
    return round(used * 100 / total, 1) if used is not None and total else None


def metrics(sample):
    """Flattens a get_telemetry snapshot into {metric: number or None} for charts and CSV."""
    values = {f"temp:{sensor['label']}": sensor["celsius"] for sensor in sample["sensors"]}
    cpu = sample["cpu"] or {}
    gpu = sample["gpu"] or {}
    usage = sample["gpu_usage"]
    memory = sample["memory"] or {}
    ram_total, ram_free = memory.get("ram_total"), memory.get("ram_available")
    swap_total, swap_free = memory.get("swap_total"), memory.get("swap_free")
    values.update(
        cpu_mhz=cpu.get("freq_avg_mhz"),
        gpu_mhz=gpu.get("freq_mhz") or (0 if gpu else None),
        cpu_load=sample["cpu_load"],
        gpu_busy=usage.get("busy_percent"),
        fan=pwm_to_percent(sample["fan_pwm"]) if sample["fan_pwm"] is not None else None,
        ram=_percent(used_bytes(ram_total, ram_free), ram_total),
        swap=_percent(used_bytes(swap_total, swap_free), swap_total),
        vram=_percent(usage.get("vram_used"), usage.get("vram_total")),
    )
    return values


class Telemetry(QObject):
    """Samples every live reading on a timer and keeps a rolling history for the charts.

    It keeps sampling while the window is hidden, so the charts cover time spent in a game.
    """

    sampled = pyqtSignal(object)

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.history = deque(maxlen=HISTORY_SECONDS * 1000 // STATUS_POLL_MS)
        self.latest = None
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(STATUS_POLL_MS)
        self._timer.timeout.connect(self.sample)

    def start(self):
        self._timer.start()
        self.sample()

    def sample(self):
        if self._busy:
            return
        self._busy = True
        self.bridge.call("get_telemetry", callback=self._sampled)

    def _sampled(self, result):
        self._busy = False
        if not result["success"]:
            return
        sample = result["data"]
        sample["metrics"] = metrics(sample)
        self.latest = sample
        self.history.append(sample)
        self.sampled.emit(sample)

    def export_csv(self, path):
        temps = []
        for sample in self.history:
            temps += [key for key in sample["metrics"] if key.startswith("temp:") and key not in temps]
        columns = temps + list(METRIC_NAMES)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["Time"] + [f"{key[5:]} (°C)" for key in temps] + list(METRIC_NAMES.values())
            )
            for sample in self.history:
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sample["time"]))
                row = [sample["metrics"].get(key) for key in columns]
                writer.writerow([stamp] + ["" if value is None else value for value in row])
        user = invoking_user()
        if user is not None and user.pw_uid != os.geteuid():
            os.chown(path, user.pw_uid, user.pw_gid)
        return len(self.history)
