from PyQt6.QtWidgets import QHBoxLayout, QPushButton

from ..common import clamp, format_freq, nearest
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, SliderRow, ToggleRow
from .base import Page


class ClockLockCard(Card):
    def __init__(self, description, fallback_step, on_apply):
        super().__init__("Manual Clock")
        self.fallback_step = fallback_step
        self.on_apply = on_apply
        self.touched = False
        self._values_key = None
        self.locked = None
        self.busy = True

        self.lock_row = self.add(InfoRow("Clock Lock"))
        self.slider = self.add(SliderRow("Clock", description, format_value=format_freq))
        self.slider.changed.connect(self._moved)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.auto_button = QPushButton("Automatic")
        self.auto_button.setObjectName("cancelBtn")
        self.auto_button.clicked.connect(lambda: self._apply(None))
        self.lock_button = QPushButton("Lock Clock")
        self.lock_button.setObjectName("primary")
        self.lock_button.clicked.connect(lambda: self._apply(self.slider.value()))
        buttons.addWidget(self.auto_button)
        buttons.addWidget(self.lock_button)
        self.add_layout(buttons)

    def _moved(self, _value):
        self.touched = True
        self._update_buttons()

    def _apply(self, mhz):
        self.touched = False
        self.on_apply(mhz)

    def update_state(self, hw_min, hw_max, steps, locked, busy, applying):
        if hw_min is None or hw_max is None or hw_min >= hw_max:
            self.hide()
            return
        self.show()
        self.locked = locked
        self.busy = busy

        values = [mhz for mhz in steps if hw_min <= mhz <= hw_max]
        if len(values) < 2:
            values = list(range(hw_min, hw_max, self.fallback_step)) + [hw_max]
        key = tuple(values)
        if key != self._values_key:
            self._values_key = key
            self.slider.set_values(
                values,
                self.slider.value() if self.touched else None,
                end_labels=(format_freq(hw_min), format_freq(hw_max)),
                reset_value=hw_max,
            )
        if not self.touched:
            preferred = locked if locked is not None else hw_max
            self.slider.set_value(clamp(nearest(preferred, values), hw_min, hw_max))

        self.lock_row.set(format_freq(locked) if locked is not None else "Automatic")
        self.slider.setEnabled(not busy)
        self.lock_button.setText("Applying…" if applying == "clock" else "Lock Clock")
        self.auto_button.setText("Applying…" if applying == "clock-auto" else "Automatic")
        self._update_buttons()

    def _update_buttons(self):
        busy = self.busy
        self.lock_button.setEnabled(not busy and self.slider.value() != self.locked)
        self.auto_button.setEnabled(not busy and self.locked is not None)


class FrequencyPage(Page):
    kind = ""
    clock_description = ""
    fallback_step = 100
    boot_note = ""
    restore_subject = ""

    def __init__(self, bridge, notify, parent=None):
        self.poll_method = f"get_{self.kind}_status"
        super().__init__(bridge, notify, parent)
        self.status = None
        self.status_error = None
        self.settings = None
        self.applying = None
        self.saving_settings = False
        self._governor_ids = None

        self.status_card = self.add(Card(f"{self.title} Frequency"))
        self.governor_row = self.status_card.add(InfoRow("Governor"))
        self.build_status_rows(self.status_card)

        self.governor_card = self.add(Card("Governors"))
        self.governor_grid = self.governor_card.add(ButtonGrid(columns=3))
        self.governor_buttons = {}
        self.governor_card.hide()

        self.clock_card = self.add(
            ClockLockCard(self.clock_description, self.fallback_step, self.apply_clock)
        )
        self.clock_card.hide()

        advanced = self.add(Card("Startup"))
        self.restore_toggle = advanced.add(ToggleRow("Restore on Startup"))
        self.restore_toggle.toggled.connect(self.save_restore)

        self.finish_layout()
        self.render()

    def build_status_rows(self, card):
        raise NotImplementedError

    def render_status_rows(self, status):
        raise NotImplementedError

    def governor_info(self, identifier):
        raise NotImplementedError

    def active_governor(self, status):
        raise NotImplementedError

    def governor_text(self, status, loading):
        if loading:
            return "…", None
        current = self.active_governor(status) if status else None
        return (self.governor_info(current)[0] if current else "Unavailable"), None

    def on_activate(self):
        self.refresh_status(callback=lambda r: self.notify(r, quiet=True))
        self.call(f"get_{self.kind}_settings", callback=self._settings_loaded)

    def _settings_loaded(self, result):
        if result["success"]:
            self.settings = result["data"]
        else:
            self.notify(result)
        self.render()

    def on_status(self, result):
        if result["success"]:
            self.status = result["data"]
            self.status_error = None
        else:
            self.status_error = result["error"]
        self.render()

    def _applied(self, result, saved_key, saved_value):
        if result["success"]:
            self.status = result["data"]
            if self.settings is not None:
                self.settings[saved_key] = saved_value(result["data"])
        self.notify(result)
        self.applying = None
        self.render()
        self.refresh_status()

    def apply_governor(self, governor):
        self.applying = governor
        self.render()
        self.call(
            f"set_{self.kind}_governor",
            governor,
            callback=lambda r: self._applied(r, "saved_governor", lambda _d: governor),
        )

    def apply_clock(self, mhz):
        self.applying = "clock-auto" if mhz is None else "clock"
        self.render()
        self.call(
            f"set_{self.kind}_clock",
            mhz,
            callback=lambda r: self._applied(r, "saved_clock", lambda d: d["locked_mhz"]),
        )

    def save_restore(self, checked):
        self.saving_settings = True
        self.render()

        def done(result):
            if result["success"]:
                self.settings = result["data"]
            self.notify(result, quiet=True)
            self.saving_settings = False
            self.render()

        self.call(f"set_{self.kind}_settings", checked, callback=done)

    def _render_governors(self, governors, current, busy):
        if governors != self._governor_ids:
            self._governor_ids = list(governors)
            self.governor_buttons = {}
            buttons = []
            for identifier in governors:
                label, description = self.governor_info(identifier)
                button = ChoiceButton(label, description)
                button.clicked.connect(lambda _=False, g=identifier: self.apply_governor(g))
                self.governor_buttons[identifier] = button
                buttons.append(button)
            self.governor_grid.set_buttons(buttons)
        self.governor_card.set_title(f"Governors ({len(governors)})")
        self.governor_card.setVisible(bool(governors))
        for identifier, button in self.governor_buttons.items():
            button.setEnabled(not busy)
            button.set_selected(identifier == current)
            button.set_busy(self.applying == identifier)

    def render(self):
        status = self.status
        loading = status is None and self.status_error is None
        busy = self.applying is not None

        value, description = self.governor_text(status, loading)
        self.governor_row.set(
            value, self.status_error or description, error=bool(self.status_error)
        )
        self.render_status_rows(status)

        current = self.active_governor(status) if status else None
        self._render_governors(status["governors"] if status else [], current, busy)

        self.clock_card.update_state(
            status["hw_min_mhz"] if status else None,
            status["hw_max_mhz"] if status else None,
            status["available_mhz"] if status else [],
            status["locked_mhz"] if status else None,
            busy,
            self.applying,
        )

        settings = self.settings
        parts = []
        if settings and settings["saved_governor"]:
            parts.append(self.governor_info(settings["saved_governor"])[0])
        if settings and settings["saved_clock"]:
            parts.append(f"the {format_freq(settings['saved_clock'])} clock lock")
        what = (
            f"Re-applies {' and '.join(parts)}"
            if parts
            else f"Re-applies your last {self.restore_subject}"
        )
        self.restore_toggle.set_description(
            f"{what} when the app or service starts. {self.boot_note}"
        )
        self.restore_toggle.set_checked(bool(settings and settings["restore_on_boot"]))
        self.restore_toggle.setEnabled(settings is not None and not self.saving_settings)
