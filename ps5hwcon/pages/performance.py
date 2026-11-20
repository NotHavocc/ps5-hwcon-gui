import os
import time

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton

from ..backend import invoking_user
from ..chart import SERIES_COLORS, LineChart
from ..telemetry import HISTORY_SECONDS
from ..widgets import ButtonGrid, Card, ChoiceButton
from .base import Page

RANGES = ((60, "1 min"), (5 * 60, "5 min"), (HISTORY_SECONDS, "10 min"))
DEFAULT_RANGE = 5 * 60
TEMP_SERIES = [(label, f"temp:{label}") for label in ("CPU", "SoC", "GPU", "GPU Junction", "SSD")]
CHARTS = (
    ("Temperatures", lambda v: f"{v:.0f} °C", None, TEMP_SERIES),
    ("Clocks", lambda v: f"{v / 1000:.1f} GHz", None, [("CPU", "cpu_mhz"), ("GPU", "gpu_mhz")]),
    ("Load", lambda v: f"{v:.0f}%", (0, 100), [("CPU", "cpu_load"), ("GPU", "gpu_busy")]),
    ("Fan Speed", lambda v: f"{v:.0f}%", (0, 100), [("Fan", "fan")]),
    ("Memory", lambda v: f"{v:.0f}%", (0, 100), [("RAM", "ram"), ("Swap", "swap"), ("VRAM", "vram")]),
)


class PerformancePage(Page):
    title = "Performance"
    needs_telemetry = True

    def __init__(self, bridge, notify, telemetry):
        super().__init__(bridge, notify)
        self.telemetry = telemetry
        self.span = DEFAULT_RANGE
        telemetry.sampled.connect(lambda _sample: self.render())

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.range_buttons = {}
        for seconds, label in RANGES:
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, s=seconds: self.set_span(s))
            self.range_buttons[seconds] = button
        ranges = ButtonGrid(columns=len(RANGES))
        ranges.set_buttons(self.range_buttons.values())
        ranges.setFixedWidth(300)
        controls.addWidget(ranges)
        controls.addStretch(1)
        export = QPushButton("Export CSV")
        export.setObjectName("small")
        export.clicked.connect(self.export_csv)
        controls.addWidget(export)
        self.body.addLayout(controls)
        ranges.setToolTip(
            "Sampled every 2 seconds and kept for 10 minutes, including while the window is "
            "hidden in the tray. Hover a chart to read values."
        )

        self.charts = []
        for title, format_value, y_range, series in CHARTS:
            card = self.add(Card(title))
            chart = card.add(LineChart(format_value, y_range))
            self.charts.append((chart, series))
        self.set_span(DEFAULT_RANGE)
        self.finish_layout()

    def set_span(self, seconds):
        self.span = seconds
        for value, button in self.range_buttons.items():
            button.set_selected(value == seconds)
        self.render(force=True)

    def on_activate(self):
        self.render()

    def render(self, force=False):
        if not (self._active or force):
            return
        history = self.telemetry.history
        now = history[-1]["time"] if history else time.time()
        recent = [s for s in history if s["time"] >= now - self.span - 5]
        for chart, definitions in self.charts:
            series = []
            for slot, (name, key) in enumerate(definitions):
                points = [(s["time"], s["metrics"].get(key)) for s in recent]
                if any(value is not None for _, value in points):
                    series.append((name, SERIES_COLORS[slot], points))
            chart.set_data(series, now, self.span)

    def export_csv(self):
        if not self.telemetry.history:
            self.notify({"success": False, "error": "There's nothing to export yet."})
            return
        user = invoking_user()
        home = user.pw_dir if user is not None else os.path.expanduser("~")
        name = time.strftime("ps5-performance-%Y%m%d-%H%M%S.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Performance History", os.path.join(home, name), "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            rows = self.telemetry.export_csv(path)
        except OSError as exc:
            self.notify({"success": False, "error": f"Couldn't save {path}: {exc.strerror or exc}"})
            return
        self.notify({"success": True, "message": f"Saved {rows} samples to {path}"})
