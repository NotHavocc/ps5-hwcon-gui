from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidget

from ..common import (
    FAN_BOOT_TARGET,
    FAN_CURVE_PRESETS,
    FAN_DEFAULT,
    FAN_MAX,
    FAN_MIN,
    FAN_MODE_CURVE,
    FAN_MODE_FIRMWARE,
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
FIRMWARE_ID = "firmware"
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


class TempTiles(QWidget):
    """A grid with a TempTile per sensor, amber near the Overheat Threshold and red at it."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(6)
        self.tiles = {}

    def set_sensors(self, sensors, threshold):
        ids = [sensor["id"] for sensor in sensors]
        if ids != list(self.tiles):
            for tile in self.tiles.values():
                self.grid.removeWidget(tile)
                tile.deleteLater()
            self.tiles = {}
            for index, sensor in enumerate(sensors):
                tile = TempTile(sensor["label"])
                self.grid.addWidget(tile, *divmod(index, TILE_COLUMNS))
                self.tiles[sensor["id"]] = tile
        for sensor in sensors:
            celsius = sensor["celsius"]
            level = "hot" if celsius >= threshold else "warm" if celsius >= threshold - GUARD_HYSTERESIS else ""
            self.tiles[sensor["id"]].set(format_temp(celsius), level)


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
        self.firmware_rows = []
        self.threshold = GUARD_DEFAULT
        self._threshold_timer = QTimer(self)
        self._threshold_timer.setSingleShot(True)
        self._threshold_timer.setInterval(SETTING_SAVE_DELAY_MS)
        self._threshold_timer.timeout.connect(
            lambda: self.save_settings(guard_threshold=self.threshold)
        )

        temps = self.add(Card("Temperatures"))
        self.tiles = temps.add(TempTiles())
        self.sensors_placeholder = temps.add(muted_label("Reading sensors…"))
        self.pro_gpu_note = temps.add(
            muted_label(
                "No GPU sensor found, check that cmdline.txt doesn't have amdgpu.ps5_smu=0"
            )
        )
        self.pro_gpu_note.hide()
        self.target_row = temps.add(InfoRow("Fan Target"))
        self.mode_row = temps.add(InfoRow("Fan Mode"))
        self.speed_row = temps.add(InfoRow("Fan Speed"))
        self.overheat_row = temps.add(InfoRow("Overheat"))
        self.overheat_row.value.setObjectName("danger")
        self.overheat_row.hide()

        control = self.add(Card("Fan Control"))
        self.view_buttons = {
            VIEW_TARGET: ChoiceButton("Target Temperature"),
            VIEW_CURVE: ChoiceButton("Fan Curve"),
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
        self._add_firmware_row(self.curve_presets_card)

        self.curve_card = self.add(Card("Fan Curve"))
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
        self._add_firmware_row(presets)

        self.manual_card = manual = self.add(Card("Manual Target"))
        self.target_slider = manual.add(
            SliderRow(
                "Target Temperature",
                "Lower targets ramp the fan earlier and louder.",
                suffix=" °C",
                hint="Lower is cooler and louder.",
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
        self.restore_toggle = advanced.add(ToggleRow("Restore on Startup", hint="Re-applies your fan setting at boot."))
        self.restore_toggle.toggled.connect(lambda c: self.save_settings(restore_on_boot=c))
        self.guard_toggle = advanced.add(ToggleRow("Thermal Guard", hint="Full speed if the CPU overheats."))
        self.guard_toggle.toggled.connect(lambda c: self.save_settings(guard_enabled=c))
        self.alarm_toggle = advanced.add(
            ToggleRow(
                "Overheat Alarm",
                "Beeps when the CPU reaches the threshold.",
                hint="Beeps if the CPU overheats.",
            )
        )
        self.alarm_toggle.toggled.connect(lambda c: self.save_settings(alarm_enabled=c))
        self.threshold_slider = advanced.add(
            SliderRow(
                "Overheat Threshold",
                "CPU temperature for Thermal Guard and the alarm.",
                suffix=" °C",
                hint="When the guard and alarm kick in.",
            )
        )
        self.threshold_slider.set_range(
            GUARD_MIN, GUARD_MAX, value=GUARD_DEFAULT, reset_value=GUARD_DEFAULT
        )
        self.threshold_slider.changed.connect(self._threshold_moved)
        self.protection_row = advanced.add(InfoRow("Protection Status"))
        self.protection_row.setToolTip("Thermal Guard and the alarm keep running in the tray and stop when you quit.")

        self.finish_layout()
        self.render()

    def _add_firmware_row(self, card):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        button = QPushButton("Return to Console Firmware")
        button.setObjectName("cancelBtn")
        button.setToolTip("Hands the fan back to the console's own fan table.")
        button.clicked.connect(lambda: self.apply_mode(FIRMWARE_ID, FAN_MODE_FIRMWARE))
        layout.addWidget(button)
        card.add(row)
        self.firmware_rows.append((row, button))

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
            self.reload_saved()

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
        self.reload_saved()

    def reload_saved(self):
        """Picks up the mode, target and curve the backend saved, for Restore on Startup's text."""

        def loaded(result):
            if result["success"] and self.settings is not None:
                for key in ("saved_target", "saved_curve", "saved_fan_mode"):
                    self.settings[key] = result["data"]["settings"][key]
                self.render()

        self.call("get_fan_settings", callback=loaded)

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

    def on_console(self):
        self.render()

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
        if self.is_pro():
            sensors = sorted(sensors, key=lambda s: s["chip"] not in ("k10temp", "amdgpu"))
        self.tiles.set_sensors(sensors, self.threshold)
        self.pro_gpu_note.setVisible(
            self.is_pro() and bool(sensors) and not any(s["chip"] == "amdgpu" for s in sensors)
        )
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
            view = VIEW_TARGET if target is not None else VIEW_CURVE
        target_view = view == VIEW_TARGET
        for view_id, button in self.view_buttons.items():
            button.set_selected(view_id == view)
            button.setEnabled(not busy and (curve_mode or view_id == VIEW_TARGET))
        note = "Fan curves need a kernel with the ps5_fan hwmon driver" if not curve_mode and not loading else ""
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
        curve_overridden = fan is not None and fan["mode"] != FAN_MODE_CURVE
        if curve_overridden:
            target_text = FAN_MODE_LABELS.get(fan["mode"], f"Mode {fan['mode']}")
        target_error = None if curve_mode else self.status_error
        self.target_row.set(target_text, target_error, error=bool(target_error))
        if curve_mode:
            self._render_curve(fan, busy)
        for row, button in self.firmware_rows:
            row.setVisible(curve_mode)
            button.setEnabled(not busy and fan is not None and fan["mode"] != FAN_MODE_FIRMWARE)
            button.setText(
                "Applying…" if self.applying == FIRMWARE_ID else "Return to Console Firmware"
            )

        overheated = bool(guard and (guard["active"] or guard["alarm_active"]))
        self.overheat_row.setVisible(overheated)
        if overheated:
            self.overheat_row.set("Cooling" if guard["active"] else "Alarm sounded")

        for preset_id, (button, temp) in self.preset_buttons.items():
            button.setEnabled(not busy)
            button.set_selected(target == temp and not curve_overridden)
            button.set_busy(self.applying == preset_id)

        self.target_slider.setEnabled(not busy)
        self.apply_button.setEnabled(
            not busy
            and not loading
            and (self.target_slider.value() != target or curve_overridden)
        )
        self.apply_button.setText("Applying…" if self.applying == "manual" else "Apply Target")

        if curve_mode:
            saved_curve = settings["saved_curve"] if settings else None
            saved_mode = settings["saved_fan_mode"] if settings else None
            if saved_mode == FAN_MODE_FIRMWARE:
                what = "Hands the fan back to the console's own control"
            elif saved_mode == FAN_MODE_FULL:
                what = "Runs the fan at full speed"
            elif saved_curve or saved_mode == FAN_MODE_CURVE:
                what = "Re-applies your fan curve"
            else:
                what = "Re-applies the last fan setting you choose"
            self.restore_toggle.set_description(f"{what} once per boot, when the app first starts.")
            self.guard_toggle.set_description(
                f"Full speed at the threshold, back to normal once {GUARD_HYSTERESIS} °C cooler."
            )
        else:
            saved = settings["saved_target"] if settings else None
            what = f"Re-applies {saved} °C" if saved is not None else "Re-applies your last target"
            self.restore_toggle.set_description(f"{what} once per boot, when the app first starts.")
            self.guard_toggle.set_description(
                f"Max Cooling at the threshold, back to your target once {GUARD_HYSTERESIS} °C cooler."
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
