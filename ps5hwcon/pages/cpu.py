from ..common import CPU_CLOCK_STEP, format_freq, governor_info, is_epp_driver
from ..widgets import InfoRow, ToggleRow, muted_label
from .freq import FrequencyPage


PRO_CPU_NOTE = "On the Pro the firmware sets CPU clocks, so these settings may do little"
BOOST_ABOUT = "Lets the CPU run above its 3.2 GHz base clock under load."


class CpuPage(FrequencyPage):
    title = "CPU"
    kind = "cpu"
    clock_description = "Pins every CPU to this clock, whatever the governor."
    fallback_step = CPU_CLOCK_STEP
    restore_subject = "governor and clock lock"

    def build_status_rows(self, card):
        self.freq_row = card.add(InfoRow("Clock"))
        self.boost_toggle = card.add(ToggleRow("Boost to 3.5 GHz", BOOST_ABOUT, hint="Faster under load."))
        self.boost_toggle.toggled.connect(self.apply_boost)
        self.boost_toggle.hide()
        self.pro_note = card.add(muted_label(PRO_CPU_NOTE))
        self.pro_note.hide()
        self.epp_note = card.add(
            muted_label("This driver only offers Performance and Powersave")
        )
        self.epp_note.hide()

    def apply_boost(self, enabled):
        self.applying = "boost"
        self.render()
        self.call(
            "set_cpu_boost",
            enabled,
            callback=lambda r: self._applied(r, "saved_boost", lambda _d: enabled),
        )

    def extra_restore_parts(self, settings):
        boost = settings.get("saved_boost")
        return [] if boost is None else [f"boost {'on' if boost else 'off'}"]

    def on_console(self):
        self.pro_note.setVisible(self.is_pro())

    def governor_info(self, identifier):
        return governor_info(identifier, self.status["driver"] if self.status else None)

    def active_governor(self, status):
        active = status["active"]
        return active[0] if len(active) == 1 else None

    def governor_text(self, status, loading):
        if status and len(status["active"]) > 1:
            return "Mixed", f"CPUs use {', '.join(status['active'])}"
        return super().governor_text(status, loading)

    def render_status_rows(self, status):
        self.freq_row.setVisible(status is not None)
        self.epp_note.setVisible(status is not None and is_epp_driver(status["driver"]))
        boost = status["boost"] if status else None
        self.boost_toggle.setVisible(boost is not None)
        if boost is not None:
            self.boost_toggle.set_checked(boost)
            self.boost_toggle.setEnabled(self.applying is None)
            self.boost_toggle.set_note("Applying…" if self.applying == "boost" else None)
        if status is None:
            return
        parts = []
        if status["freq_peak_mhz"] is not None:
            parts.append(f"Peak {format_freq(status['freq_peak_mhz'])}")
        if status["locked_mhz"] is not None:
            parts.append(f"Locked at {format_freq(status['locked_mhz'])}")
        elif status["hw_min_mhz"] is not None and status["hw_max_mhz"] is not None:
            parts.append(
                f"Range {format_freq(status['hw_min_mhz'])} – {format_freq(status['hw_max_mhz'])}"
            )
        average = status["freq_avg_mhz"]
        self.freq_row.set(format_freq(average) if average is not None else "Unknown")
        self.freq_row.setToolTip("\n".join(parts + [f"Driver: {status['driver'] or 'unknown'}"]))
