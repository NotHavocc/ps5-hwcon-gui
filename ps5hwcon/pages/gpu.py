from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton

from ..common import GPU_CLOCK_STEP, format_freq, gpu_governor_info
from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, SliderRow, ToggleRow, muted_label, short_text
from .boot_options import BootOptionRow
from .freq import FrequencyPage


PRO_FULL_CUS = 60
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
GPU_NOTE = "While the CPU boosts, the firmware holds the GPU at 2.23 GHz whatever you set here."
GPU_NOTE_PRO = "Shows Idle while the GPU clock is gated off."
TEMP_LIMIT_ABOUT = "Where the GPU starts slowing down. Lower is cooler but slower."
TEMP_LIMIT_WARNING = (
    "Above {default} °C the GPU runs hotter and louder. The old cmdline.txt is kept as "
    "cmdline.txt.bak."
)
VIOLA_ENV_CHOICES = (
    (
        "AMD_VIOLA_COMPUTE_QUEUE",
        "Hide Compute Queue",
        "AMD_VIOLA_COMPUTE_QUEUE=0: hides the async compute queue from games.",
        "Try it if a game glitches.",
    ),
    (
        "RADV_VIOLA_ML",
        "Stock int8 Path",
        "RADV_VIOLA_ML=0: uses the stock int8 path.",
        "Skips the Pro's int8 instructions.",
    ),
)
VIOLA_ENV_ABOUT = (
    "Applies to every session after you log out and back in. Needs a Mesa with the Pro patches."
)
OLD_KERNEL_NOTE = "Its CPU clock driver is too old for the Pro (mp1fw_sendmsg busy), update it"
COREDUMP_ABOUT = (
    "Left by a GPU fault, which the Pro can't recover from. The kernel deletes it after about "
    "5 minutes."
)
BT_RESYNC_ABOUT = "Adds btusb.ps5_ep_resync=1 to cmdline.txt so the Pro's Bluetooth works."
BT_RESYNC_MISSING = "Needs rmuxnet's kernel."
STUTTER_ABOUT = "Removes idle=halt from cmdline.txt. Try it if games micro-stutter."
COMPUTE_QUEUE_ABOUT = (
    "AMD_PS5_COMPUTE_QUEUE=0: try it if one game shows a corrupted picture or hangs. Only matters "
    "with PS5 Bazzite Deck's Mesa. Applies after you log out and back in."
)


class GpuPage(FrequencyPage):
    title = "GPU"
    kind = "gpu"
    clock_description = "Pins the GPU to this clock, whatever the governor."
    fallback_step = GPU_CLOCK_STEP
    restore_subject = "GPU governor and clock lock"

    def build_status_rows(self, card):
        self.pro_status = None
        self.clock_row = card.add(InfoRow("Clock"))
        self.gpu_note = GPU_NOTE

    def build_extra_cards(self):
        self.build_temp_limit_card()
        self.build_pro_card()
        self.build_cu_card()
        self.build_games_card()
        self.render_console()

    def build_temp_limit_card(self):
        self.limit_state = None
        self.limit_saving = False
        self.limit_touched = False
        self.limit_range = None
        card = self.limit_card = self.add(Card("Thermal Limit"))
        self.limit_row = card.add(InfoRow("Current"))
        self.limit_slider = card.add(SliderRow("Limit", TEMP_LIMIT_ABOUT, suffix=" °C", hint="Lower is cooler but slower."))
        self.limit_slider.changed.connect(self._limit_moved)
        self.limit_note = card.add(muted_label())
        self.limit_button = QPushButton("Save")
        self.limit_button.setObjectName("primary")
        self.limit_button.clicked.connect(self.save_temp_limit)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.limit_button)
        card.add_layout(row)
        self.render_temp_limit()

    def build_pro_card(self):
        self.pro_saving = None
        self.pro_card = self.add(Card("PS5 Pro"))
        self.bt_state = None
        self.bt_saving = False
        self.dump_saving = False
        self.pro_kernel_row = self.pro_card.add(InfoRow("Kernel"))
        self.pro_kernel_row.hide()
        self.pro_cu_row = self.pro_card.add(InfoRow("Active CUs"))
        self.pro_toggles = {}
        for name, label, description, hint in VIOLA_ENV_CHOICES:
            toggle = self.pro_card.add(ToggleRow(label, f"{description} {VIOLA_ENV_ABOUT}", hint=hint))
            toggle.toggled.connect(lambda checked, n=name: self.save_viola_env(n, checked))
            self.pro_toggles[name] = toggle

        self.bt_toggle = self.pro_card.add(ToggleRow("Bluetooth Fix", BT_RESYNC_ABOUT, hint="Makes the Pro's Bluetooth work."))
        self.bt_toggle.toggled.connect(self.save_bt_resync)

        self.dump_row = self.pro_card.add(InfoRow("GPU Crash Dump"))
        self.dump_button = QPushButton("Save Dump")
        self.dump_button.clicked.connect(self.save_coredump)
        dump_buttons = QHBoxLayout()
        dump_buttons.addStretch(1)
        dump_buttons.addWidget(self.dump_button)
        self.pro_card.add_layout(dump_buttons)

    def build_cu_card(self):
        self.cu_state = None
        self.cu_saving = None
        card = self.cu_card = self.add(Card("CU Unlock"))
        self.cu_row = card.add(InfoRow("Active CUs"))
        self.cu_buttons = {}
        for target, label in CU_CHOICES:
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, t=target: self.save_cu_unlock(t))
            self.cu_buttons[target] = button
        card.add(ButtonGrid(columns=len(CU_CHOICES))).set_buttons(self.cu_buttons.values())
        card.setToolTip(CU_UNLOCK_ABOUT)
        self.cu_note = card.add(muted_label())
        self.cu_reload_note = card.add(muted_label())
        self.cu_reload_button = QPushButton("Apply Now")
        self.cu_reload_button.clicked.connect(self.reload_cu_unlock)
        reload_row = QHBoxLayout()
        reload_row.addStretch(1)
        reload_row.addWidget(self.cu_reload_button)
        card.add_layout(reload_row)
        self.render_cu()

    def build_games_card(self):
        self.boot_state = None
        self.compute_hidden = None
        self.games_saving = None
        card = self.games_card = self.add(Card("Games"))
        self.stutter_toggle = card.add(
            BootOptionRow(
                "idle_halt", "Micro-stutter Fix", STUTTER_ABOUT, inverted=True, hint="Try it if games stutter."
            )
        )
        self.stutter_toggle.toggled.connect(self.save_stutter_fix)
        self.compute_toggle = card.add(ToggleRow("Hide Compute Queue", COMPUTE_QUEUE_ABOUT, hint="Try it if a game glitches."))
        self.compute_toggle.toggled.connect(self.save_compute_queue)
        self.render_games()

    def save_stutter_fix(self, checked):
        wanted = self.stutter_toggle.wanted(checked)
        self._save_game_setting("set_boot_option", ("idle_halt", wanted), "boot_state")

    def save_compute_queue(self, checked):
        self._save_game_setting("set_compute_queue", (checked,), "compute_hidden")

    def _save_game_setting(self, method, args, attribute):
        self.games_saving = attribute
        self.render_games()

        def done(result):
            self.notify(result)
            self.games_saving = None
            self._game_setting_loaded(attribute, result)

        self.call(method, *args, callback=done)

    def _game_setting_loaded(self, attribute, result):
        if result["success"]:
            data = result["data"]
            setattr(self, attribute, data["hidden"] if attribute == "compute_hidden" else data)
        self.render_games()

    def render_games(self):
        busy = self.games_saving is not None
        self.stutter_toggle.render(self.boot_state, busy)
        self.compute_toggle.set_checked(bool(self.compute_hidden))
        self.compute_toggle.setEnabled(self.compute_hidden is not None and not busy)
        self.compute_toggle.setVisible(self.console is not None and not self.is_pro())

    def on_activate(self):
        super().on_activate()
        self.games_saving = None
        self.call("get_boot_options", callback=lambda r: self._game_setting_loaded("boot_state", r))
        self.call("get_compute_queue", callback=lambda r: self._game_setting_loaded("compute_hidden", r))
        self.cu_saving = None
        self.limit_saving = False
        self.pro_saving = None
        self.call("get_gpu_temp_limit", callback=self._limit_loaded)
        self.load_model_details()

    def on_console(self):
        self.render_console()
        if self._active:
            self.load_model_details()

    def load_model_details(self):
        if self.console is None:
            return
        if self.is_pro():
            self.call("get_pro_status", callback=self._pro_status_loaded)
            self.call("get_bt_resync", callback=self._bt_loaded)
        else:
            self.call("get_cu_unlock", callback=self._cu_loaded)

    def _pro_status_loaded(self, result):
        if result["success"]:
            self.pro_status = result["data"]
        self.notify(result, quiet=True)
        self.render_console()

    def _bt_loaded(self, result):
        if result["success"]:
            self.bt_state = result["data"]
        self.notify(result, quiet=True)
        self.render_console()

    def save_bt_resync(self, enabled):
        self.bt_saving = True
        self.render_console()

        def done(result):
            if result["success"]:
                self.bt_state = result["data"]
            self.notify(result)
            self.bt_saving = False
            self.render_console()

        self.call("set_bt_resync", enabled, callback=done)

    def save_coredump(self):
        self.dump_saving = True
        self.render_console()

        def done(result):
            self.notify(result)
            self.dump_saving = False
            self.render_console()

        self.call("save_gpu_coredump", callback=done)

    def render_pro_extras(self, status):
        old_kernel = bool(status and status["old_kernel"])
        self.pro_kernel_row.setVisible(old_kernel)
        if old_kernel:
            self.pro_kernel_row.set("Too old", OLD_KERNEL_NOTE, error=True)

        bt = self.bt_state
        if bt is None:
            self.bt_toggle.set_note(None)
            ready = False
        elif not bt["supported"]:
            self.bt_toggle.set_note(BT_RESYNC_MISSING)
            ready = False
        elif bt["cmdline_path"] is None:
            self.bt_toggle.set_note(bt["boot_error"], error=True)
            ready = False
        else:
            self.bt_toggle.set_note("Reboot to apply." if bt["pending"] else None)
            ready = True
        self.bt_toggle.set_checked(bool(bt and bt["configured"]))
        self.bt_toggle.setEnabled(ready and not self.bt_saving)

        dump = status["coredump"] if status else None
        self.dump_row.set("Available" if dump else "None")
        self.dump_row.setToolTip(COREDUMP_ABOUT)
        self.dump_button.setVisible(bool(dump))
        self.dump_button.setEnabled(not self.dump_saving)
        self.dump_button.setText("Saving…" if self.dump_saving else "Save Dump")

    def arrange_cards(self, pro):
        if pro:
            order = (self.status_card, self.pro_card, self.limit_card, self.governor_card,
                     self.clock_card, self.games_card, self.cu_card)
        else:
            order = (self.status_card, self.governor_card, self.clock_card,
                     self.limit_card, self.cu_card, self.games_card, self.pro_card)
        for index, card in enumerate(order):
            if self.body.indexOf(card) != index:
                self.body.removeWidget(card)
                self.body.insertWidget(index, card)

    def render_console(self):
        console = self.console
        pro = self.is_pro()
        self.gpu_note = GPU_NOTE_PRO if pro else GPU_NOTE
        self.arrange_cards(pro)
        self.render_games()
        self.cu_card.setVisible(console is not None and not pro)
        self.pro_card.setVisible(pro)
        self.render_status_rows(self.status)
        if not pro:
            return

        status = self.pro_status
        active = status["active_cus"] if status else None
        if status is None:
            self.pro_cu_row.set("…")
        elif active is None:
            self.pro_cu_row.set("Unknown", "Not found in dmesg.")
        elif active < PRO_FULL_CUS or status["viola_firmware"] is False:
            self.pro_cu_row.set(
                str(active),
                "Viola firmware not loaded, start Linux again (twice after a system update)",
                error=True,
            )
        else:
            self.pro_cu_row.set(str(active))

        self.render_pro_extras(status)
        env = status["viola_env"] if status else {}
        for name, toggle in self.pro_toggles.items():
            toggle.set_checked(bool(env.get(name)))
            toggle.setEnabled(status is not None and self.pro_saving is None)

    def save_viola_env(self, name, enabled):
        self.pro_saving = name
        self.render_console()

        def done(result):
            if result["success"]:
                self.pro_status = result["data"]
            self.notify(result)
            self.pro_saving = None
            self.render_console()

        self.call("set_viola_env", name, enabled, callback=done)

    def _limit_loaded(self, result):
        if result["success"]:
            self.limit_state = result["data"]
            self.limit_touched = False
        self.notify(result, quiet=True)
        self.render_temp_limit()

    def _limit_moved(self, _value):
        self.limit_touched = True
        self.render_temp_limit()

    def save_temp_limit(self):
        state = self.limit_state
        value = self.limit_slider.value()
        if value > state["default"] and value > state["configured"]:
            answer = QMessageBox.warning(
                self,
                f"Raise GPU Thermal Limit to {value} °C",
                TEMP_LIMIT_WARNING.format(default=state["default"]),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                return
        self.limit_saving = True
        self.render_temp_limit()

        def done(result):
            if result["success"]:
                self.limit_state = result["data"]
                self.limit_touched = False
            self.notify(result)
            self.limit_saving = False
            self.render_temp_limit()

        self.call("set_gpu_temp_limit", value, callback=done)

    def render_temp_limit(self):
        state = self.limit_state
        if state is None:
            self.limit_row.hide()
            self.limit_note.hide()
            self.limit_slider.setEnabled(False)
            self.limit_button.setEnabled(False)
            return

        limit_range = (state["min"], state["max"], state["default"])
        if limit_range != self.limit_range:
            self.limit_range = limit_range
            self.limit_slider.set_range(state["min"], state["max"], reset_value=state["default"])
        configured = state["configured"]
        if not self.limit_touched:
            self.limit_slider.set_value(configured or state["running"])
        self.limit_row.setVisible(bool(state["pending"]))
        if state["pending"]:
            self.limit_row.set(f"{state['running']} °C", f"{configured} °C after a reboot.")

        note = None
        if not state["supported"]:
            note = "This kernel doesn't have the ps5-gpufreq driver, so the limit does nothing"
        elif state["cmdline_path"] is None:
            note = (
                f"{short_text(state['boot_error'])}\nOr add ps5_gpufreq.temp_limit=<50-95> to "
                "cmdline.txt by hand"
            )
        self.limit_note.setText(note or "")
        self.limit_note.setVisible(bool(note))

        ready = state["cmdline_path"] is not None and not self.limit_saving
        self.limit_slider.setEnabled(ready)
        self.limit_button.setText("Saving…" if self.limit_saving else "Save")
        self.limit_button.setEnabled(ready and self.limit_slider.value() != configured)

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
            self.cu_note.hide()
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
            note = "This kernel doesn't include the CU unlock (amdgpu.ps5_cu_unlock)"
        elif state["cmdline_path"] is None:
            note = f"{short_text(state['boot_error'])}\nOr add amdgpu.ps5_cu_unlock=3 to cmdline.txt by hand"
        elif state["pending"]:
            note = "Reboot to apply"
            blocker = state["reload_blocker"]
            self.cu_reload_note.setText(
                short_text(blocker) or "Or apply it now by reloading the GPU driver (experimental)"
            )
            self.cu_reload_note.show()
            self.cu_reload_button.setVisible(blocker is None)
            self.cu_reload_button.setEnabled(self.cu_saving is None)
        else:
            note = ""
        self.cu_note.setText(note)
        self.cu_note.setVisible(bool(note))
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
        if freq is not None:
            clock = format_freq(freq)
        else:
            clock = "Idle" if self.is_pro() else "Unknown"
        self.clock_row.set(clock)
        self.clock_row.setToolTip("\n".join(parts + [self.gpu_note, f"Device: {status['device']}"]))
