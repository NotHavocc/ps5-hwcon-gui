from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..common import (
    CURATED_LED_PRESETS,
    LED_LOOP_DEFAULT,
    LED_LOOP_MAX,
    LED_LOOP_MIN,
    SETTING_SAVE_DELAY_MS,
    prettify,
)
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, SliderRow, ToggleRow, muted_label
from .base import Page


class PresetRow(QWidget):
    def __init__(self, preset, on_apply):
        super().__init__()
        self.setObjectName("presetRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.preset = preset
        self.search_text = f"{preset} {prettify(preset).lower()}"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 6)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.name = QLabel(prettify(preset))
        self.tags = muted_label(word_wrap=False)
        text.addWidget(self.name)
        text.addWidget(self.tags)
        layout.addLayout(text, 1)
        self.button = QPushButton("Apply")
        self.button.setObjectName("small")
        self.button.clicked.connect(lambda: on_apply(preset))
        layout.addWidget(self.button)

    def update_state(self, tags, busy, pending):
        self.tags.setText(tags)
        self.tags.setVisible(bool(tags))
        self.button.setEnabled(not busy)
        self.button.setText("Applying…" if pending else "Apply")


class LedPage(Page):
    title = "LED"

    def __init__(self, bridge, notify, parent=None):
        super().__init__(bridge, notify, parent)
        self.presets = None
        self.animated = set()
        self.loading = True
        self.pending = None
        self.active = None
        self.error = None
        self.loop = None
        self.loop_seconds = LED_LOOP_DEFAULT
        self.saving_loop = False
        self._rows = {}
        self._loop_timer = QTimer(self)
        self._loop_timer.setSingleShot(True)
        self._loop_timer.setInterval(SETTING_SAVE_DELAY_MS)
        self._loop_timer.timeout.connect(lambda: self.save_loop(None, self.loop_seconds))

        presets = self.add(Card("Quick Presets"))
        self.active_row = presets.add(InfoRow("Active Preset"))
        self.curated_grid = presets.add(ButtonGrid(columns=3))
        self.curated_buttons = {}
        buttons = []
        for preset_id, label in CURATED_LED_PRESETS:
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, p=preset_id: self.apply(p))
            self.curated_buttons[preset_id] = button
            buttons.append(button)
        self.curated_grid.set_buttons(buttons)
        refresh_row = QHBoxLayout()
        refresh_row.addStretch(1)
        self.refresh_button = QPushButton("Refresh Presets")
        self.refresh_button.clicked.connect(lambda: self.refresh(quiet=False))
        refresh_row.addWidget(self.refresh_button)
        presets.add_layout(refresh_row)

        animations = self.add(Card("Animations"))
        self.loop_toggle = animations.add(
            ToggleRow(
                "Loop Animations",
                "The firmware plays breathe and pulse animations once. This replays them so "
                "they keep going, even with the window closed to the tray.",
            )
        )
        self.loop_toggle.toggled.connect(lambda checked: self.save_loop(checked, None))
        self.loop_slider = animations.add(
            SliderRow("Replay Every", "Match this to how long the animation runs.", suffix=" s")
        )
        self.loop_slider.set_range(
            LED_LOOP_MIN, LED_LOOP_MAX, value=LED_LOOP_DEFAULT, reset_value=LED_LOOP_DEFAULT
        )
        self.loop_slider.changed.connect(self._loop_seconds_moved)
        self.loop_row = animations.add(InfoRow("Loop Status"))

        startup = self.add(Card("Startup"))
        self.restore_toggle = startup.add(ToggleRow("Restore on Startup"))
        self.restore_toggle.toggled.connect(lambda checked: self.save_loop(None, None, checked))

        self.all_card = self.add(Card("All Presets"))
        self.filter = self.all_card.add(QLineEdit())
        self.filter.setPlaceholderText("Filter presets…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _text: self.render())
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.all_card.add(self.list_container)
        self.no_match = self.all_card.add(muted_label("No presets match"))
        self.all_card.hide()

        self.finish_layout()
        self.render()

    def on_activate(self):
        self.refresh(quiet=True)
        self.call("get_led_settings", callback=self._settings_loaded)

    def _settings_loaded(self, result):
        if result["success"]:
            self.loop = result["data"]
            self.loop_seconds = self.loop["loop_seconds"]
            self.loop_slider.set_value(self.loop_seconds)
            self.active = self.loop["preset"]
        else:
            self.notify(result)
        self.render()

    def refresh(self, quiet):
        self.loading = True
        self.render()

        def done(result):
            if result["success"]:
                self.presets = result["data"]["presets"]
                self.animated = set(result["data"]["animated"])
                self.error = None
            else:
                self.presets = None
                self.error = result["error"]
            self.notify(result, quiet=quiet)
            self.loading = False
            self.render()

        self.call("get_led_presets", callback=done)

    def apply(self, preset):
        self.pending = preset
        self.render()

        def done(result):
            if result["success"]:
                self.active = result["data"]["preset"]
                self.loop = result["data"]
            self.notify(result)
            self.pending = None
            self.render()

        self.call("set_led_preset", preset, callback=done)

    def save_loop(self, enabled, seconds, restore=None):
        self.saving_loop = True
        self.render()

        def done(result):
            if result["success"]:
                self.loop = result["data"]
            self.notify(result, quiet=True)
            self.saving_loop = False
            self.render()

        self.call("set_led_settings", enabled, seconds, restore, callback=done)

    def _loop_seconds_moved(self, value):
        self.loop_seconds = value
        self._loop_timer.start()

    def deactivate(self):
        if self._loop_timer.isActive():
            self._loop_timer.stop()
            self.save_loop(None, self.loop_seconds)
        super().deactivate()

    def _sync_rows(self):
        presets = self.presets or []
        if list(self._rows) == presets:
            return
        for row in self._rows.values():
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows = {}
        for preset in presets:
            row = PresetRow(preset, self.apply)
            self.list_layout.addWidget(row)
            self._rows[preset] = row

    def _tags(self, preset, loop_enabled):
        if self.active == preset:
            return "Active · looping" if loop_enabled and preset in self.animated else "Active"
        return "Animated" if preset in self.animated else ""

    def render(self):
        busy = self.loading or self.pending is not None
        loop_enabled = bool(self.loop and self.loop["loop_enabled"])
        available = set(self.presets or [])

        if self.loading:
            active_text = "…"
        else:
            active_text = prettify(self.active) if self.active else "Unknown"
        self.active_row.set(active_text, self.error, error=bool(self.error))

        for preset_id, button in self.curated_buttons.items():
            usable = self.presets is None or preset_id in available or preset_id == "off"
            button.setEnabled(not busy and usable)
            button.set_selected(self.active == preset_id)
            button.set_busy(self.pending == preset_id)
        self.refresh_button.setEnabled(not busy)
        self.refresh_button.setText("Refreshing…" if self.loading else "Refresh Presets")

        self.loop_toggle.set_checked(loop_enabled)
        self.loop_toggle.setEnabled(self.loop is not None and not self.saving_loop)
        self.loop_slider.setEnabled(loop_enabled)
        if loop_enabled and self.loop["looping"] and self.active:
            loop_status = f"Looping {prettify(self.active)}"
        elif loop_enabled:
            loop_status = "Waiting for an animated preset"
        else:
            loop_status = "Off"
        self.loop_row.set(loop_status)

        saved_preset = self.loop["saved_preset"] if self.loop else None
        what = (
            f"Re-applies {prettify(saved_preset)}"
            if saved_preset
            else "Re-applies your last LED preset"
        )
        self.restore_toggle.set_description(
            f"{what} when the app or service starts. The kernel picks its default LED at boot."
        )
        self.restore_toggle.set_checked(bool(self.loop and self.loop["restore_on_boot"]))
        self.restore_toggle.setEnabled(self.loop is not None and not self.saving_loop)

        self._sync_rows()
        self.all_card.setVisible(bool(self.presets))
        self.all_card.set_title(f"All Presets ({len(self.presets or [])})")
        query = self.filter.text().strip().lower()
        shown = 0
        for preset, row in self._rows.items():
            visible = not query or query in row.search_text
            row.setVisible(visible)
            shown += visible
            row.update_state(self._tags(preset, loop_enabled), busy, self.pending == preset)
        self.no_match.setVisible(bool(self.presets) and shown == 0)
