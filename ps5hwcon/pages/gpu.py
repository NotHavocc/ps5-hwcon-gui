from ..common import GPU_CLOCK_STEP, format_freq, gpu_governor_info
from ..widgets import InfoRow, muted_label
from .freq import FrequencyPage


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
