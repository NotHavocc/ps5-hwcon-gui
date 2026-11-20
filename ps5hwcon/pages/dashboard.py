from PyQt6.QtWidgets import QGridLayout, QLabel, QProgressBar, QWidget

from ..common import (
    FAN_MODE_LABELS,
    GUARD_DEFAULT,
    format_freq,
    format_temp,
    governor_info,
    gpu_governor_info,
    pwm_to_percent,
)
from ..telemetry import used_bytes
from ..widgets import Card, InfoRow, muted_label
from .base import Page
from .fan import TempTiles
from .memory import format_usage

CORE_COLUMNS = 4


class CoreBar(QWidget):
    def __init__(self, index):
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        label = QLabel(str(index))
        label.setObjectName("muted")
        label.setFixedWidth(16)
        self.bar = QProgressBar()
        self.bar.setObjectName("load")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setMinimumWidth(24)
        layout.addWidget(label, 0, 0)
        layout.addWidget(self.bar, 0, 1)

    def set(self, percent):
        self.bar.setValue(round(percent))
        self.setToolTip(f"{percent:.0f}%")


def _usage(used, total):
    if used is None or not total:
        return "Unknown"
    return f"{format_usage(used)} of {format_usage(total)} ({used * 100 / total:.0f}%)"


class DashboardPage(Page):
    title = "Dashboard"
    needs_telemetry = True

    def __init__(self, bridge, notify, telemetry):
        super().__init__(bridge, notify)
        self.telemetry = telemetry
        telemetry.sampled.connect(self.render)

        temps = self.add(Card("Temperatures"))
        self.tiles = temps.add(TempTiles())
        self.placeholder = temps.add(muted_label("Reading sensors…"))

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        cpu = Card("CPU")
        self.cpu_clock = cpu.add(InfoRow("Clock"))
        self.cpu_governor = cpu.add(InfoRow("Governor"))
        self.cpu_load = cpu.add(InfoRow("Load"))
        self.cores_grid = QGridLayout()
        self.cores_grid.setHorizontalSpacing(12)
        self.cores_grid.setVerticalSpacing(4)
        cpu.add_layout(self.cores_grid)
        self.cores = []

        gpu = Card("GPU")
        self.gpu_clock = gpu.add(InfoRow("Clock"))
        self.gpu_governor = gpu.add(InfoRow("Governor"))
        self.gpu_busy = gpu.add(InfoRow("Busy"))
        self.vram = gpu.add(InfoRow("VRAM"))

        fan = Card("Fan")
        self.fan_speed = fan.add(InfoRow("Speed"))
        self.fan_mode = fan.add(InfoRow("Mode"))

        memory = Card("Memory")
        self.ram = memory.add(InfoRow("RAM"))
        self.swap = memory.add(InfoRow("Swap"))

        grid.addWidget(cpu, 0, 0)
        grid.addWidget(gpu, 0, 1)
        grid.addWidget(fan, 1, 0)
        grid.addWidget(memory, 1, 1)
        self.finish_layout()

    def on_activate(self):
        if self.telemetry.latest is not None:
            self.render(self.telemetry.latest)

    def render(self, sample):
        if not self._active:
            return
        self.render_temps(sample["sensors"])
        self.render_cpu(sample)
        self.render_gpu(sample)
        pwm = sample["fan_pwm"]
        self.fan_speed.set(f"{pwm_to_percent(pwm)}%" if pwm is not None else "Unknown")
        mode = sample["fan_mode"]
        if mode is not None:
            self.fan_mode.set(FAN_MODE_LABELS.get(mode, f"Mode {mode}"))
        elif sample["fan_target"] is not None:
            self.fan_mode.set(f"Target {format_temp(sample['fan_target'])}")
        else:
            self.fan_mode.set("Unknown")
        memory = sample["memory"] or {}
        total, free = memory.get("ram_total"), memory.get("ram_available")
        self.ram.set(_usage(used_bytes(total, free), total))
        swap_total = memory.get("swap_total")
        self.swap.set(_usage(used_bytes(swap_total, memory.get("swap_free")), swap_total) if swap_total else "Off")

    def render_temps(self, sensors):
        self.placeholder.setVisible(not sensors)
        if not sensors:
            self.placeholder.setText("No temperature sensors found")
        self.tiles.set_sensors(sensors, GUARD_DEFAULT)

    def render_cpu(self, sample):
        cpu = sample["cpu"]
        if cpu is None:
            for row in (self.cpu_clock, self.cpu_governor):
                row.set("Unavailable")
        else:
            mhz = cpu["freq_avg_mhz"]
            self.cpu_clock.set(format_freq(mhz) if mhz is not None else "Unknown")
            names = [governor_info(g, cpu["driver"])[0] for g in cpu["active"]]
            self.cpu_governor.set(", ".join(names) or "Unknown")
        load = sample["cpu_load"]
        self.cpu_load.set(f"{load:.0f}%" if load is not None else "…")
        core_loads = sample["core_loads"]
        if len(core_loads) != len(self.cores):
            for bar in self.cores:
                self.cores_grid.removeWidget(bar)
                bar.deleteLater()
            self.cores = [CoreBar(index) for index in range(len(core_loads))]
            for index, bar in enumerate(self.cores):
                self.cores_grid.addWidget(bar, *divmod(index, CORE_COLUMNS))
        for bar, percent in zip(self.cores, core_loads):
            bar.set(percent)

    def render_gpu(self, sample):
        gpu = sample["gpu"]
        if gpu is None:
            for row in (self.gpu_clock, self.gpu_governor):
                row.set("Unavailable")
        else:
            mhz = gpu["freq_mhz"]
            self.gpu_clock.set(format_freq(mhz) if mhz is not None else "Idle" if self.is_pro() else "Unknown")
            self.gpu_governor.set(gpu_governor_info(gpu["active"])[0] if gpu["active"] else "Unknown")
        usage = sample["gpu_usage"]
        busy = usage.get("busy_percent")
        self.gpu_busy.set(f"{busy}%" if busy is not None else "Unknown")
        self.vram.set(_usage(usage.get("vram_used"), usage.get("vram_total")))
