from ..widgets import ToggleRow

BOOT_OPTIONS_NOTE = "Saved in cmdline.txt on the boot drive. The previous version is kept as cmdline.txt.bak."


class BootOptionRow(ToggleRow):
    """A cmdline.txt option. With `inverted`, the box is ticked while the argument is absent."""

    def __init__(self, key, label, description, inverted=False, hint=""):
        super().__init__(label, description, hint=hint)
        self.key = key
        self.inverted = inverted

    def wanted(self, checked):
        """Whether the argument should be in cmdline.txt for a ticked or cleared box."""
        return checked != self.inverted

    def render(self, state, busy):
        option = state["options"][self.key] if state else None
        configured = option["configured"] if option else None
        self.set_checked(bool(configured is not None and configured != self.inverted))
        ready = bool(option and state["cmdline_path"] and not busy)
        if option and not option["supported"]:
            self.set_note("Not in this kernel.")
            self.setEnabled(ready and configured is True)
            return
        self.setEnabled(ready)
        if state and not state["cmdline_path"]:
            self.set_note(state["boot_error"], error=True)
        else:
            self.set_note("Reboot to apply." if option and option["pending"] else None)
