from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidget

from ..common import (
    FAN_BOOT_TARGET,
    FAN_CURVE_PRESETS,
    FAN_DEFAULT,
    FAN_MAX,
    FAN_MAX_COOLING,
    FAN_MIN,
    FAN_MODE_CURVE,
    FAN_MODE_FULL,
    FAN_MODE_LABELS,
    FAN_PRESETS,
    FAN_QUIET_STOP,
    FAN_QUIET_TEMPS,
    GUARD_DEFAULT,
    GUARD_HYSTERESIS,
    GUARD_MAX,
    GUARD_MIN,
    SETTING_SAVE_DELAY_MS,
    clamp,
    format_temp,
    pwm_to_percent,
)
from ..curve_editor import CurveEditor
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, SliderRow, ToggleRow, muted_label, restyle
from .base import Page

TILE_COLUMNS = 2
FULL_SPEED_ID = "full"
VIEW_TARGET = "target"
VIEW_CURVE = "curve"


def curve_preset_id(curve):
    for preset_id, _label, _subtitle, preset in FAN_CURVE_PRESETS:
        if preset is None:
            temps = [temp for temp, _pwm in curve["points"]]
            if temps == FAN_QUIET_TEMPS and curve["stop"] == FAN_QUIET_STOP:
                return preset_id
        elif curve == preset:
            return preset_id
    return None


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
        self.curve_touched = False
        self.view = None
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
        self.mode_row = temps.add(InfoRow("Fan Mode"))
        self.speed_row = temps.add(InfoRow("Fan Speed"))
        self.overheat_row = temps.add(InfoRow("Overheat"))
        self.overheat_row.value.setObjectName("danger")
        self.overheat_row.hide()

        control = self.add(Card("Fan Control"))
        self.view_buttons = {
            VIEW_TARGET: ChoiceButton("Target Temperature", "Holds the SoC near a temperature"),
            VIEW_CURVE: ChoiceButton("Fan Curve", "Fan speed per temperature"),
        }
        for view, button in self.view_buttons.items():
            button.clicked.connect(lambda _=False, v=view: self._select_view(v))
        control.add(ButtonGrid(columns=2)).set_buttons(list(self.view_buttons.values()))
        self.view_note = control.add(muted_label())

        self.curve_presets_card = self.add(Card("Presets"))
        self.curve_preset_buttons = {}
        buttons = []
        for preset_id, label, subtitle, curve in FAN_CURVE_PRESETS:
            button = ChoiceButton(label, subtitle)
            button.clicked.connect(lambda _=False, p=preset_id, c=curve: self.apply_curve(p, c))
            self.curve_preset_buttons[preset_id] = button
            buttons.append(button)
        full = ChoiceButton("Full Speed", "Ignores the curve")
        full.clicked.connect(lambda: self.apply_mode(FULL_SPEED_ID, FAN_MODE_FULL))
        self.curve_preset_buttons[FULL_SPEED_ID] = full
        buttons.append(full)
        self.curve_presets_card.add(ButtonGrid(columns=2)).set_buttons(buttons)

        self.curve_card = self.add(Card("Fan Curve"))
        self.curve_card.add(
            muted_label(
                "Drag the points to set the fan speed for each SoC temperature. The diamond is "
                "where the fan stops; between it and the first point the fan keeps its last "
                "state. Above 90 °C the kernel always takes over."
            )
        )
        self.curve_editor = self.curve_card.add(CurveEditor())
        self.curve_editor.changed.connect(self._curve_edited)
        curve_buttons = QHBoxLayout()
        curve_buttons.addStretch(1)
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("cancelBtn")
        self.revert_button.clicked.connect(self._revert_curve)
        self.apply_curve_button = QPushButton("Apply Curve")
        self.apply_curve_button.setObjectName("primary")
        self.apply_curve_button.clicked.connect(
            lambda: self.apply_curve("custom", self.curve_editor.curve())
        )
        curve_buttons.addWidget(self.revert_button)
        curve_buttons.addWidget(self.apply_curve_button)
        self.curve_card.add_layout(curve_buttons)

        self.presets_card = presets = self.add(Card("Presets"))
        self.preset_grid = presets.add(ButtonGrid(columns=3))
        self.preset_buttons = {}
        buttons = []
        for preset_id, label, temp in FAN_PRESETS:
            button = ChoiceButton(label, f"{temp} °C")
            button.clicked.connect(lambda _=False, p=preset_id, t=temp: self.apply_target(p, t))
            self.preset_buttons[preset_id] = (button, temp)
            buttons.append(button)
        self.preset_grid.set_buttons(buttons)

        self.manual_card = manual = self.add(Card("Manual Target"))
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
        self.guard_toggle = advanced.add(ToggleRow("Thermal Guard"))
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
            if self.status["fan_error"]:
                self.status_error = self.status["fan_error"]
            if not self.slider_touched and self.status["target"] is not None:
                self.target_slider.set_value(clamp(self.status["target"], FAN_MIN, FAN_MAX))
            fan = self.status["fan"]
            if fan is not None:
                if not self.curve_touched:
                    self.curve_editor.set_curve(fan["curve"])
                self.curve_editor.set_live(fan["temp"], fan["pwm"])
        else:
            self.status_error = result["error"]
        self.render()

    def apply_target(self, source, temp):
        self.applying = source
        self.render()

        def done(result):
            if result["success"]:
                data = result["data"]
                if self.status is not None:
                    self.status["target"] = data["temp"]
                    fan = self.status["fan"]
                    if fan is not None and "curve" in data:
                        fan.update({key: data[key] for key in ("curve", "mode") if key in data})
                        self.curve_editor.set_curve(data["curve"])
                        self.curve_touched = False
                self.target_slider.set_value(temp)
                self.slider_touched = False
            self.notify(result)
            self.applying = None
            self.render()
            self.refresh_status()

        self.call("set_fan_target", temp, callback=done)

    def _fan_done(self, result):
        if result["success"] and self.status is not None and self.status["fan"] is not None:
            data = result["data"] or {}
            fan = self.status["fan"]
            fan.update({key: data[key] for key in ("curve", "mode") if key in data})
            if "curve" in data:
                self.curve_editor.set_curve(data["curve"])
                self.curve_touched = False
        self.notify(result)
        self.applying = None
        self.render()
        self.refresh_status()

    def apply_curve(self, source, curve):
        self.applying = source
        self.render()
        if curve is None:
            self.call("reset_fan_curve", callback=self._fan_done)
        else:
            self.call("set_fan_curve", curve, callback=self._fan_done)

    def apply_mode(self, source, mode):
        self.applying = source
        self.render()
        self.call("set_fan_mode", mode, callback=self._fan_done)

    def _select_view(self, view):
        self.view = view
        self.render()

    def _curve_edited(self):
        self.curve_touched = True
        self.render()

    def _revert_curve(self):
        fan = self.status["fan"] if self.status else None
        if fan is not None:
            self.curve_editor.set_curve(fan["curve"])
        self.curve_touched = False
        self.render()

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

        curve_mode = bool(status and status["interface"] == "curve")
        fan = status["fan"] if curve_mode else None
        if not curve_mode:
            view = VIEW_TARGET
        elif self.view is not None:
            view = self.view
        else:
            # Open on whatever is driving the fan: a target-built curve, or any other curve.
            view = VIEW_TARGET if target is not None else VIEW_CURVE
        target_view = view == VIEW_TARGET
        for view_id, button in self.view_buttons.items():
            button.set_selected(view_id == view)
            button.setEnabled(not busy and (curve_mode or view_id == VIEW_TARGET))
        if not curve_mode and not loading:
            note = "Fan curves need a kernel with the ps5_fan hwmon driver."
        elif curve_mode and target_view:
            note = (
                "This kernel controls the fan by curve, so the target is applied as a curve that "
                "ramps up to full speed just above it. Editing the curve replaces the target."
            )
        else:
            note = ""
        self.view_note.setText(note)
        self.view_note.setVisible(bool(note))

        for widget in (self.mode_row, self.speed_row):
            widget.setVisible(curve_mode)
        for widget in (self.curve_presets_card, self.curve_card):
            widget.setVisible(curve_mode and not target_view)
        for widget in (self.target_row, self.presets_card, self.manual_card):
            widget.setVisible(target_view)

        if loading:
            target_text = "…"
        elif target is not None:
            target_text = f"{target} °C"
        else:
            target_text = "Custom curve" if fan is not None else "Unavailable"
        target_error = None if curve_mode else self.status_error
        self.target_row.set(target_text, target_error, error=bool(target_error))
        if curve_mode:
            self._render_curve(fan, busy)

        overheated = bool(guard and (guard["active"] or guard["alarm_active"]))
        self.overheat_row.setVisible(overheated)
        if overheated:
            self.overheat_row.set("Cooling" if guard["active"] else "Alarm sounded")

        for preset_id, (button, temp) in self.preset_buttons.items():
            button.setEnabled(not busy)
            button.set_selected(
                target == temp and not (fan is not None and fan["mode"] == FAN_MODE_FULL)
            )
            button.set_busy(self.applying == preset_id)

        self.target_slider.setEnabled(not busy)
        self.apply_button.setEnabled(
            not busy and not loading and self.target_slider.value() != target
        )
        self.apply_button.setText("Applying…" if self.applying == "manual" else "Apply Target")

        if curve_mode:
            saved_curve = settings["saved_curve"] if settings else None
            what = (
                "Re-applies your saved target or fan curve"
                if saved_curve
                else "Re-applies the last target or curve you apply"
            )
            self.restore_toggle.set_description(
                f"{what} when the app or service starts. "
                "The kernel resets the curve to its quiet default at boot."
            )
            self.guard_toggle.set_description(
                "Run the fan at full speed when the CPU reaches the threshold, then go back to "
                f"the previous mode once it is {GUARD_HYSTERESIS} °C cooler."
            )
        else:
            saved = settings["saved_target"] if settings else None
            what = f"Re-applies {saved} °C" if saved is not None else "Re-applies your last target"
            self.restore_toggle.set_description(
                f"{what} when the app or service starts. "
                f"The kernel resets the target to {FAN_BOOT_TARGET} °C at boot."
            )
            self.guard_toggle.set_description(
                f"Switch to Max Cooling ({FAN_MAX_COOLING} °C) when the CPU reaches the "
                f"threshold, then restore your target once it is {GUARD_HYSTERESIS} °C cooler."
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
        if guard_enabled and guard and guard["active"] and guard["kind"] == "curve":
            guard_status = "Cooling · full speed"
        elif guard_enabled and guard and guard["active"]:
            restore = guard["restore_target"] or FAN_BOOT_TARGET
            guard_status = f"Cooling · restores {restore} °C"
        elif alarm_enabled and guard and guard["alarm_active"]:
            guard_status = "Overheated · alarm sounded"
        elif protection_enabled and guard and guard["cpu"] is not None:
            guard_status = f"Standby · CPU {format_temp(guard['cpu'])}"
        elif protection_enabled:
            guard_status = "Standby"
        self.protection_row.set(guard_status)

    def _render_curve(self, fan, busy):
        error = self.status_error
        if fan is None:
            self.mode_row.set("Unavailable", error, error=bool(error))
            self.speed_row.set("Unavailable")
        else:
            mode = fan["mode"]
            self.mode_row.set(FAN_MODE_LABELS.get(mode, f"Mode {mode}"), error, error=bool(error))
            pwm = fan["pwm"]
            self.speed_row.set(f"{pwm_to_percent(pwm)}%" if pwm is not None else "Unavailable")

        selected = None
        if fan is not None:
            if fan["mode"] == FAN_MODE_FULL:
                selected = FULL_SPEED_ID
            elif fan["mode"] == FAN_MODE_CURVE:
                selected = curve_preset_id(fan["curve"])
        for preset_id, button in self.curve_preset_buttons.items():
            button.setEnabled(not busy and fan is not None)
            button.set_selected(preset_id == selected)
            button.set_busy(self.applying == preset_id)

        edited = fan is not None and self.curve_editor.curve() != fan["curve"]
        self.curve_editor.setEnabled(not busy and fan is not None)
        self.revert_button.setEnabled(not busy and edited)
        self.apply_curve_button.setEnabled(
            not busy and fan is not None and (edited or fan["mode"] != FAN_MODE_CURVE)
        )
        self.apply_curve_button.setText(
            "Applying…" if self.applying == "custom" else "Apply Curve"
        )
