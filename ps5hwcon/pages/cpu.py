from ..common import CPU_CLOCK_STEP, format_freq, governor_info
from ..widgets import InfoRow, muted_label
from .freq import FrequencyPage


class CpuPage(FrequencyPage):
    title = "CPU"
    kind = "cpu"
    clock_description = "Pins every CPU to this clock, whatever the governor."
    fallback_step = CPU_CLOCK_STEP
    restore_subject = "governor and clock lock"
    boot_note = "The kernel picks its default governor and clock range at boot."

    def build_status_rows(self, card):
        self.freq_row = card.add(InfoRow("Frequency"))
        self.driver_row = card.add(InfoRow("Driver"))
        card.add(
            muted_label(
                "With an EPP driver such as amd-pstate-epp, the kernel only offers Performance "
                "and Powersave. The firmware still manages clocks under Powersave."
            )
        )

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
        self.driver_row.setVisible(status is not None)
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
        self.freq_row.set(
            format_freq(average) if average is not None else "Unknown", " · ".join(parts)
        )
        self.driver_row.set(
            status["driver"] or "Unknown", f"{status['policy_count']} frequency policies"
        )
