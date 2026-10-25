from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidget

from ..common import (
    FAN_BOOT_TARGET,
    FAN_DEFAULT,
    FAN_MAX,
    FAN_MAX_COOLING,
    FAN_MIN,
    FAN_PRESETS,
    GUARD_DEFAULT,
    GUARD_HYSTERESIS,
    GUARD_MAX,
    GUARD_MIN,
    SETTING_SAVE_DELAY_MS,
    clamp,
    format_temp,
)
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, SliderRow, ToggleRow, muted_label, restyle
from .base import Page

TILE_COLUMNS = 2


class TempTile(QWidget):
    def __init__(self, label):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        self.label = QLabel(f"{label}:")
        self.value = QLabel("…")
        self.value.setObjectName("tileValue")
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set(self, value, level=""):
        self.value.setText(value)
        if self.value.property("level") != level:
            self.value.setProperty("level", level)
            restyle(self.value)


class FanPage(Page):
    title = "Fan"
    poll_method = "get_fan_status"

    def __init__(self, bridge, notify, parent=None):
        super().__init__(bridge, notify, parent)
        self.status = None
        self.status_error = None
        self.settings = None
        self.applying = None
        self.saving_settings = False
        self.slider_touched = False
        self.threshold = GUARD_DEFAULT
        self._threshold_timer = QTimer(self)
        self._threshold_timer.setSingleShot(True)
        self._threshold_timer.setInterval(SETTING_SAVE_DELAY_MS)
        self._threshold_timer.timeout.connect(
            lambda: self.save_settings(guard_threshold=self.threshold)
        )

        temps = self.add(Card("Temperatures"))
        self.tiles_grid = QGridLayout()
        self.tiles_grid.setHorizontalSpacing(24)
        self.tiles_grid.setVerticalSpacing(6)
        temps.add_layout(self.tiles_grid)
        self.tiles = {}
        self.sensors_placeholder = temps.add(muted_label("Reading sensors…"))
        self.target_row = temps.add(InfoRow("Fan Target"))
        self.overheat_row = temps.add(InfoRow("Overheat"))
        self.overheat_row.value.setObjectName("danger")
        self.overheat_row.hide()

        presets = self.add(Card("Presets"))
        self.preset_grid = presets.add(ButtonGrid(columns=3))
        self.preset_buttons = {}
        buttons = []
        for preset_id, label, temp in FAN_PRESETS:
            button = ChoiceButton(label, f"{temp} °C")
            button.clicked.connect(lambda _=False, p=preset_id, t=temp: self.apply_target(p, t))
            self.preset_buttons[preset_id] = (button, temp)
            buttons.append(button)
        self.preset_grid.set_buttons(buttons)

        manual = self.add(Card("Manual Target"))
        self.target_slider = manual.add(
            SliderRow(
                "Target Temperature",
                "Lower targets ramp the fan earlier and louder.",
                suffix=" °C",
            )
        )
        self.target_slider.set_range(FAN_MIN, FAN_MAX, value=FAN_DEFAULT, reset_value=FAN_DEFAULT)
        self.target_slider.changed.connect(self._slider_moved)
        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        self.apply_button = QPushButton("Apply Target")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(
            lambda: self.apply_target("manual", self.target_slider.value())
        )
        apply_row.addWidget(self.apply_button)
        manual.add_layout(apply_row)

        advanced = self.add(Card("Protection && Startup"))
        self.restore_toggle = advanced.add(ToggleRow("Restore on Startup"))
        self.restore_toggle.toggled.connect(lambda c: self.save_settings(restore_on_boot=c))
        self.guard_toggle = advanced.add(
            ToggleRow(
                "Thermal Guard",
                f"Switch to Max Cooling ({FAN_MAX_COOLING} °C) when the CPU reaches the "
                f"threshold, then restore your target once it is {GUARD_HYSTERESIS} °C cooler.",
            )
        )
        self.guard_toggle.toggled.connect(lambda c: self.save_settings(guard_enabled=c))
        self.alarm_toggle = advanced.add(
            ToggleRow(
                "Overheat Alarm",
                "Play the console's error beep when the CPU reaches the threshold. "
                f"It re-arms once the CPU is {GUARD_HYSTERESIS} °C cooler.",
            )
        )
        self.alarm_toggle.toggled.connect(lambda c: self.save_settings(alarm_enabled=c))
        self.threshold_slider = advanced.add(
            SliderRow(
                "Overheat Threshold",
                "CPU temperature used by Thermal Guard and Overheat Alarm.",
                suffix=" °C",
            )
        )
        self.threshold_slider.set_range(
            GUARD_MIN, GUARD_MAX, value=GUARD_DEFAULT, reset_value=GUARD_DEFAULT
        )
        self.threshold_slider.changed.connect(self._threshold_moved)
        self.protection_row = advanced.add(InfoRow("Protection Status"))
        background = muted_label(
            "Thermal Guard and Overheat Alarm keep running while the window is closed to the "
            "tray, or all the time when the headless service is installed."
        )
        advanced.add(background)

        self.finish_layout()
        self.render()

    def on_activate(self):
        self.refresh_status(callback=lambda r: self.notify(r, quiet=True))
        self.call("get_fan_settings", callback=self._settings_loaded)

    def _settings_loaded(self, result):
        if result["success"]:
            self.settings = result["data"]["settings"]
            self.threshold = self.settings["guard_threshold"]
            self.threshold_slider.set_value(self.threshold)
        else:
            self.notify(result)
        self.render()

    def on_status(self, result):
        if result["success"]:
            self.status = result["data"]
            self.status_error = self.status["target_error"]
            if not self.slider_touched and self.status["target"] is not None:
                self.target_slider.set_value(clamp(self.status["target"], FAN_MIN, FAN_MAX))
        else:
            self.status_error = result["error"]
        self.render()

    def apply_target(self, source, temp):
        self.applying = source
        self.render()

        def done(result):
            if result["success"]:
                if self.status is not None:
                    self.status["target"] = result["data"]["temp"]
                self.target_slider.set_value(temp)
                self.slider_touched = False
            self.notify(result)
            self.applying = None
            self.render()
            self.refresh_status()

        self.call("set_fan_target", temp, callback=done)

    def save_settings(
        self, restore_on_boot=None, guard_enabled=None, guard_threshold=None, alarm_enabled=None
    ):
        self.saving_settings = True
        self.render()

        def done(result):
            if result["success"]:
                self.settings = result["data"]["settings"]
                if self.status is not None:
                    self.status["guard"] = result["data"]["guard"]
            self.notify(result, quiet=True)
            self.saving_settings = False
            self.render()

        self.call(
            "set_fan_settings",
            restore_on_boot,
            guard_enabled,
            guard_threshold,
            alarm_enabled,
            callback=done,
        )

    def _slider_moved(self, _value):
        self.slider_touched = True
        self.render()

    def _threshold_moved(self, value):
        self.threshold = value
        self._threshold_timer.start()

    def deactivate(self):
        if self._threshold_timer.isActive():
            self._threshold_timer.stop()
            self.save_settings(guard_threshold=self.threshold)
        super().deactivate()

    def _render_sensors(self, sensors, threshold):
        ids = [sensor["id"] for sensor in sensors]
        if ids != list(self.tiles):
            for tile in self.tiles.values():
                self.tiles_grid.removeWidget(tile)
                tile.deleteLater()
            self.tiles = {}
            for index, sensor in enumerate(sensors):
                tile = TempTile(sensor["label"])
                self.tiles_grid.addWidget(tile, *divmod(index, TILE_COLUMNS))
                self.tiles[sensor["id"]] = tile
        for sensor in sensors:
            celsius = sensor["celsius"]
            level = "hot" if celsius >= threshold else "warm" if celsius >= threshold - GUARD_HYSTERESIS else ""
            self.tiles[sensor["id"]].set(format_temp(celsius), level)

    def render(self):
        status = self.status
        loading = status is None and self.status_error is None
        target = status["target"] if status else None
        guard = status["guard"] if status else None
        busy = self.applying is not None
        settings = self.settings
        guard_enabled = bool(settings and settings["guard_enabled"])
        alarm_enabled = bool(settings and settings["alarm_enabled"])
        protection_enabled = guard_enabled or alarm_enabled

        sensors = status["sensors"] if status else []
        self._render_sensors(sensors, self.threshold)
        self.sensors_placeholder.setText(
            "Reading sensors…" if loading else "No temperature sensors found"
        )
        self.sensors_placeholder.setVisible(not sensors)

        if loading:
            target_text = "…"
        else:
            target_text = f"{target} °C" if target is not None else "Unavailable"
        self.target_row.set(target_text, self.status_error, error=bool(self.status_error))

        overheated = bool(guard and (guard["active"] or guard["alarm_active"]))
        self.overheat_row.setVisible(overheated)
        if overheated:
            self.overheat_row.set("Cooling" if guard["active"] else "Alarm sounded")

        for preset_id, (button, temp) in self.preset_buttons.items():
            button.setEnabled(not busy)
            button.set_selected(target == temp)
            button.set_busy(self.applying == preset_id)

        self.target_slider.setEnabled(not busy)
        self.apply_button.setEnabled(
            not busy and not loading and self.target_slider.value() != target
        )
        self.apply_button.setText("Applying…" if self.applying == "manual" else "Apply Target")

        saved = settings["saved_target"] if settings else None
        what = f"Re-applies {saved} °C" if saved is not None else "Re-applies your last target"
        self.restore_toggle.set_description(
            f"{what} when the app or service starts. "
            f"The kernel resets the target to {FAN_BOOT_TARGET} °C at boot."
        )
        toggles_enabled = settings is not None and not self.saving_settings
        for toggle, key in (
            (self.restore_toggle, "restore_on_boot"),
            (self.guard_toggle, "guard_enabled"),
            (self.alarm_toggle, "alarm_enabled"),
        ):
            toggle.set_checked(bool(settings and settings[key]))
            toggle.setEnabled(toggles_enabled)
        self.threshold_slider.setEnabled(protection_enabled)

        guard_status = "Off"
        if guard_enabled and guard and guard["active"]:
            restore = guard["restore_target"] or FAN_BOOT_TARGET
            guard_status = f"Cooling · restores {restore} °C"
        elif alarm_enabled and guard and guard["alarm_active"]:
            guard_status = "Overheated · alarm sounded"
        elif protection_enabled and guard and guard["cpu"] is not None:
            guard_status = f"Standby · CPU {format_temp(guard['cpu'])}"
        elif protection_enabled:
            guard_status = "Standby"
        self.protection_row.set(guard_status)
