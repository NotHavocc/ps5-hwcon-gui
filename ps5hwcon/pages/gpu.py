from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton

from ..common import GPU_CLOCK_STEP, format_freq, gpu_governor_info
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, muted_label
from .freq import FrequencyPage


CU_CHOICES = ((0, "Off"), (38, "38 CUs"), (40, "40 CUs"))
CU_ARGUMENTS = {38: "amdgpu.ps5_cu_unlock=3 amdgpu.disable_cu=0.0.0", 40: "amdgpu.ps5_cu_unlock=3"}
CU_UNLOCK_MODES = {
    0: "Off",
    1: "Probe only",
    2: "First shader array only",
    3: "All CUs",
    4: "Probe only",
}
CU_UNLOCK_ABOUT = (
    "Turns on the CUs disabled at the factory, which only happens at boot, so this edits "
    "cmdline.txt on your boot drive. Consoles have 36 or 38 active CUs out of 40. If games "
    "glitch, try RADV_DEBUG=nohiz, or turn this off."
)
CU_UNLOCK_WARNING = (
    "This adds {arguments} to cmdline.txt and takes effect after a reboot.\n\n"
    "Some of the disabled CUs can be faulty, which causes visual glitches. 38 CUs turns them "
    "all on and then masks one fixed pair, so it may not avoid a faulty one. If the screen is "
    "unusable after rebooting, remove the arguments from cmdline.txt over SSH or from another "
    "computer. The previous version is saved as cmdline.txt.bak."
)
CU_RELOAD_WARNING = (
    "This applies the change now by reloading the GPU driver, but it's VERY experimental.\n\n"
    "Everything on screen closes and you may be logged out, so save your work first. This app "
    "quits too, which stops Thermal Guard and LED loops until you open it again.\n\n"
    "If the screen stays black, restart the console. The change stays in cmdline.txt, so if the "
    "black screen comes back, remove it over SSH or from another computer."
)


class GpuPage(FrequencyPage):
    title = "GPU"
    kind = "gpu"
    clock_description = (
        "Pins the GPU to this clock, whatever the governor. "
        "The firmware still overrides it while the CPU boosts."
    )
    fallback_step = GPU_CLOCK_STEP
    restore_subject = "GPU governor and clock lock"
    boot_note = "The kernel starts the GPU on Ondemand at boot."

    def build_status_rows(self, card):
        self.clock_row = card.add(InfoRow("Clock"))
        self.device_row = card.add(InfoRow("Device"))
        card.add(
            muted_label(
                "GPU governors need a kernel built with CONFIG_PS5_GPUFREQ. While the CPU runs "
                "at a boost clock (3.3–3.5 GHz), the firmware holds the GPU at its 2.23 GHz "
                "ceiling, regardless of the governor or clock lock."
            )
        )

    def build_extra_cards(self):
        self.cu_state = None
        self.cu_saving = None
        card = self.add(Card("CU Unlock"))
        self.cu_row = card.add(InfoRow("Active CUs"))
        self.cu_buttons = {}
        for target, label in CU_CHOICES:
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, t=target: self.save_cu_unlock(t))
            self.cu_buttons[target] = button
        card.add(ButtonGrid(columns=len(CU_CHOICES))).set_buttons(self.cu_buttons.values())
        self.cu_note = card.add(muted_label())
        self.cu_reload_note = card.add(muted_label())
        self.cu_reload_button = QPushButton("Apply Now")
        self.cu_reload_button.clicked.connect(self.reload_cu_unlock)
        reload_row = QHBoxLayout()
        reload_row.addStretch(1)
        reload_row.addWidget(self.cu_reload_button)
        card.add_layout(reload_row)
        self.render_cu()

    def on_activate(self):
        super().on_activate()
        self.cu_saving = None
        self.call("get_cu_unlock", callback=self._cu_loaded)

    def _cu_loaded(self, result):
        if result["success"]:
            self.cu_state = result["data"]
        self.notify(result, quiet=True)
        self.render_cu()

    def save_cu_unlock(self, target):
        if target == self.cu_state["configured_target"]:
            return
        if target:
            answer = QMessageBox.warning(
                self,
                f"Unlock {target} CUs",
                CU_UNLOCK_WARNING.format(arguments=CU_ARGUMENTS[target]),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                return
        self.cu_saving = target
        self.render_cu()

        def done(result):
            if result["success"]:
                self.cu_state = result["data"]
            self.notify(result)
            self.cu_saving = None
            self.render_cu()

        self.call("set_cu_unlock", target, callback=done)

    def reload_cu_unlock(self):
        answer = QMessageBox.warning(
            self,
            "Reload GPU Driver",
            CU_RELOAD_WARNING,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self.cu_saving = "reload"
        self.render_cu()

        def done(result):
            self.notify(result, quiet=True)
            self.cu_saving = None
            self.render_cu()
            if result["success"]:
                self.window().quit()

        self.call("reload_cu_unlock", callback=done)

    def render_cu(self):
        state = self.cu_state
        self.cu_reload_note.hide()
        self.cu_reload_button.hide()
        if state is None:
            self.cu_row.set("…")
            self.cu_note.setText(CU_UNLOCK_ABOUT)
            for button in self.cu_buttons.values():
                button.setEnabled(False)
            return

        active = state["active_cus"]
        running = state["running"]
        supported = running is not None
        mode = CU_UNLOCK_MODES.get(running, f"Mode {running}")
        if state["running_target"] == 38:
            mode = "38 CUs"
        elif state["running_mask"]:
            mode = f"{mode}, masked {state['running_mask']}"
        self.cu_row.set(
            str(active) if active is not None else "Unknown",
            f"Unlock this boot: {mode}" if supported else None,
        )
        if not supported:
            note = "This kernel doesn't include the CU unlock (amdgpu.ps5_cu_unlock)."
        elif state["cmdline_path"] is None:
            note = (
                f"{state['boot_error']} You can also add amdgpu.ps5_cu_unlock=3 to cmdline.txt "
                "by hand."
            )
        elif state["pending"]:
            note = f"{CU_UNLOCK_ABOUT} Reboot to apply your change."
            blocker = state["reload_blocker"]
            self.cu_reload_note.setText(
                blocker or "Or apply it now by reloading the GPU driver (experimental)."
            )
            self.cu_reload_note.show()
            self.cu_reload_button.setVisible(blocker is None)
            self.cu_reload_button.setEnabled(self.cu_saving is None)
        else:
            note = CU_UNLOCK_ABOUT
        self.cu_note.setText(note)
        ready = supported and state["cmdline_path"] is not None
        for target, button in self.cu_buttons.items():
            button.setEnabled(ready and self.cu_saving is None)
            button.set_selected(state["configured_target"] == target)
            button.set_busy(self.cu_saving == target)

    def governor_info(self, identifier):
        return gpu_governor_info(identifier)

    def active_governor(self, status):
        return status["active"]

    def render_status_rows(self, status):
        self.clock_row.setVisible(status is not None)
        self.device_row.setVisible(status is not None)
        if status is None:
            return
        parts = []
        if status["target_mhz"] is not None:
            parts.append(f"Target {format_freq(status['target_mhz'])}")
        if status["locked_mhz"] is not None:
            parts.append(f"Locked at {format_freq(status['locked_mhz'])}")
        elif status["min_mhz"] is not None and status["max_mhz"] is not None:
            parts.append(f"Range {format_freq(status['min_mhz'])} – {format_freq(status['max_mhz'])}")
        freq = status["freq_mhz"]
        self.clock_row.set(format_freq(freq) if freq is not None else "Unknown", " · ".join(parts))
        self.device_row.set(status["device"])
