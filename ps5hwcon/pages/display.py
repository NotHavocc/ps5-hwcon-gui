from PyQt6.QtWidgets import QHBoxLayout, QPushButton

from ..widgets import Card, InfoRow
from .base import Page
from .boot_options import BOOT_OPTIONS_NOTE, BootOptionRow

DISPLAY_OPTIONS = (
    (
        "force_1080p",
        "1080p Safe Mode",
        "Only allows 1080p at 60 Hz, to get a picture back. Turn it off afterwards.",
        "Gets a picture back.",
    ),
    (
        "no_4k120",
        "No 4K at 120 Hz",
        "Never offers 4K at 120 Hz. Try it if 4K120 flickers or drops out.",
        "Try it if 4K120 flickers.",
    ),
    ("no_vrr", "No VRR", "Never offers variable refresh rate.", "Turns off variable refresh."),
    (
        "no_cec_wake",
        "Don't Wake the TV",
        "Doesn't turn the TV on and switch it to the console at boot.",
        "The TV stays off at boot.",
    ),
    (
        "usbc_dp",
        "Front USB-C Display",
        "DisplayPort on the front USB-C port, for USB-C displays and the PS VR2. "
        "Not with the boot drive in that port.",
        "For USB-C displays and PS VR2.",
    ),
)


def _yes(value):
    return value is not None and value.strip().upper() in ("Y", "1")


class DisplayPage(Page):
    title = "Display"

    def __init__(self, bridge, notify):
        super().__init__(bridge, notify)
        self.state = None
        self.saving = None
        self.retrying = False

        self.link_card = self.add(Card("HDMI Link"))
        self.frl_row = self.link_card.add(InfoRow("4K 120 Hz Link"))
        self.retry_button = QPushButton("Retry 4K 120 Hz")
        self.retry_button.clicked.connect(self.retry_frl)
        retry_row = QHBoxLayout()
        retry_row.addStretch(1)
        retry_row.addWidget(self.retry_button)
        self.link_card.add_layout(retry_row)
        self.link_card.hide()

        options = self.add(Card("Boot Options"))
        self.rows = []
        for key, label, description, hint in DISPLAY_OPTIONS:
            row = options.add(BootOptionRow(key, label, description, hint=hint))
            row.toggled.connect(lambda checked, r=row: self.save_option(r, checked))
            self.rows.append(row)
        options.setToolTip(BOOT_OPTIONS_NOTE)
        self.finish_layout()
        self.render()

    def on_activate(self):
        self.saving = None
        self.call("get_boot_options", callback=self._loaded)

    def _loaded(self, result):
        if result["success"]:
            self.state = result["data"]
        else:
            self.notify(result)
        self.render()

    def save_option(self, row, checked):
        self.saving = row.key

        def done(result):
            self.notify(result)
            self.saving = None
            self._loaded(result) if result["success"] else self.render()

        self.render()
        self.call("set_boot_option", row.key, row.wanted(checked), callback=done)

    def retry_frl(self):
        self.retrying = True

        def done(result):
            self.notify(result)
            self.retrying = False
            self.call("get_boot_options", callback=self._loaded)

        self.render()
        self.call("retry_hdmi_frl", callback=done)

    def render(self):
        state = self.state
        for row in self.rows:
            row.render(state, self.saving is not None)
        hdmi = state["hdmi"] if state else None
        self.link_card.setVisible(hdmi is not None)
        if hdmi is None:
            return
        failed = _yes(hdmi["frl_failed"])
        self.frl_row.set(
            "Failed" if failed else "OK",
            "Fell back to a slower link." if failed else None,
            error=failed,
        )
        self.frl_row.setToolTip(
            f"FRL rate {hdmi['frl_rate'] or '?'} of {hdmi['frl_rate_max'] or '?'} · "
            f"Auto low latency {'on' if _yes(hdmi['allm_active']) else 'off'} · "
            f"Recovery {hdmi['recovery_status'] or 'unknown'}"
        )
        self.retry_button.setVisible(failed)
        self.retry_button.setEnabled(not self.retrying)
        self.retry_button.setText("Retrying…" if self.retrying else "Retry 4K 120 Hz")
