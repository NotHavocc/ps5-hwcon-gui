from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..widgets import ButtonGrid, Card, ChoiceButton, InfoRow, ToggleRow, muted_label
from .base import Page


MIB = 1024 * 1024
GIB = 1024 * MIB
TOO_SMALL_VRAM = 256 * MIB
RECOMMENDED_VRAM_MB = 6 * 1024
CUSTOM_VRAM_MIN_GB = 0.25
CUSTOM_VRAM_MAX_GB = 12
VRAM_CHOICES = (
    (512, "512 MB", "Loader default"),
    (1024, "1 GB", ""),
    (2048, "2 GB", ""),
    (4096, "4 GB", ""),
    (RECOMMENDED_VRAM_MB, "6 GB", "Recommended"),
    (8192, "8 GB", ""),
)
GTT_CHOICES = ((None, "Default"), (10, "10 GB"), (12, "12 GB"))
ZRAM_SIZES = (("ram / 4", "Quarter", "ram / 4"), ("ram / 2", "Half", "ram / 2"), ("ram", "All", "ram"))
ZRAM_ALGORITHMS = (("zstd", "zstd", "Best ratio"), ("lz4", "lz4", "Fastest"), ("lzo-rle", "lzo-rle", ""))
DEFAULT_ZRAM_SIZE = "ram / 2"
DEFAULT_ZRAM_ALGORITHM = "zstd"

OVERVIEW_ABOUT = (
    "The CPU and GPU share one 16 GB pool, about 14 GB of it usable by Linux. Memory given to "
    "the GPU is taken from everything else."
)
VRAM_ABOUT = (
    "Memory reserved for the GPU all the time, taken from system RAM. 6 GB is the usual choice "
    "for gaming."
)
GTT_ABOUT = (
    "How much system RAM the GPU can use on top of that. If a game runs out of memory, raise "
    "this first, because the RAM stays free when you aren't gaming."
)
ZRAM_ABOUT = (
    "A compressed swap device in RAM. It's fast and doesn't wear out a drive, but the "
    "compressed pages still use RAM. Saved in /etc/systemd/zram-generator.conf and applied "
    "after a reboot."
)
ZSWAP_ABOUT = (
    "Compresses pages in RAM before they're written to a swap file or partition. It only helps "
    "with swap on a drive. With zram it compresses everything twice, so leave it off."
)


def format_bytes(size):
    if size >= GIB:
        return f"{size / GIB:g} GB"
    return f"{size // MIB} MB" if size >= MIB else f"{size} bytes"


def format_usage(size):
    return f"{size / GIB:.1f} GB" if size >= GIB else f"{size // MIB} MB"


class MemoryPage(Page):
    title = "Memory"
    poll_method = "get_memory_status"

    def __init__(self, bridge, notify, parent=None):
        super().__init__(bridge, notify, parent)
        self.status = None
        self.status_error = None
        self.memory = None
        self.memory_saving = None
        self.swap = None
        self.swap_saving = None

        overview = self.add(Card("Overview"))
        self.ram_row = overview.add(InfoRow("RAM"))
        self.swap_row = overview.add(InfoRow("Swap"))
        overview.add(muted_label(OVERVIEW_ABOUT))

        self.build_gpu_card()
        self.build_zram_card()
        self.build_zswap_card()
        self.finish_layout()
        self.render()

    def build_gpu_card(self):
        card = self.add(Card("GPU Memory"))
        self.vram_row = card.add(InfoRow("VRAM"))
        self.vram_buttons = {}
        for megabytes, label, subtitle in VRAM_CHOICES:
            button = ChoiceButton(label, subtitle)
            button.clicked.connect(lambda _=False, m=megabytes: self.save_vram(m))
            self.vram_buttons[megabytes] = button
        card.add(ButtonGrid(columns=3)).set_buttons(self.vram_buttons.values())

        custom = QHBoxLayout()
        custom.setSpacing(8)
        custom.addWidget(QLabel("Custom:"))
        self.vram_input = QLineEdit()
        self.vram_input.setPlaceholderText(f"{RECOMMENDED_VRAM_MB // 1024}")
        self.vram_input.setToolTip(f"{CUSTOM_VRAM_MIN_GB:g} – {CUSTOM_VRAM_MAX_GB:g} GB")
        self.vram_input.textChanged.connect(lambda _text: self.render_memory())
        self.vram_input.returnPressed.connect(self.save_custom_vram)
        custom.addWidget(self.vram_input, 1)
        custom.addWidget(QLabel("GB"))
        self.vram_custom_button = QPushButton("Set")
        self.vram_custom_button.clicked.connect(self.save_custom_vram)
        custom.addWidget(self.vram_custom_button)
        card.add_layout(custom)
        card.add(muted_label(VRAM_ABOUT))

        self.gtt_row = card.add(InfoRow("GTT Limit"))
        self.gtt_buttons = {}
        for gigabytes, label in GTT_CHOICES:
            button = ChoiceButton(label)
            button.clicked.connect(
                lambda _=False, g=gigabytes: self.save_memory("set_gtt_limit", g)
            )
            self.gtt_buttons[gigabytes] = button
        card.add(ButtonGrid(columns=len(GTT_CHOICES))).set_buttons(self.gtt_buttons.values())
        card.add(muted_label(GTT_ABOUT))

    def build_zram_card(self):
        card = self.add(Card("zram"))
        self.zram_row = card.add(InfoRow("zram"))
        self.zram_toggle = card.add(ToggleRow("Enable zram", ZRAM_ABOUT))
        self.zram_toggle.toggled.connect(lambda checked: self.save_zram(enabled=checked))
        card.add(QLabel("Size"))
        self.zram_size_buttons = {}
        for size, label, subtitle in ZRAM_SIZES:
            button = ChoiceButton(label, subtitle)
            button.clicked.connect(lambda _=False, s=size: self.save_zram(size=s))
            self.zram_size_buttons[size] = button
        card.add(ButtonGrid(columns=len(ZRAM_SIZES))).set_buttons(self.zram_size_buttons.values())
        card.add(QLabel("Compression"))
        self.zram_algorithm_buttons = {}
        for algorithm, label, subtitle in ZRAM_ALGORITHMS:
            button = ChoiceButton(label, subtitle)
            button.clicked.connect(lambda _=False, a=algorithm: self.save_zram(algorithm=a))
            self.zram_algorithm_buttons[algorithm] = button
        card.add(ButtonGrid(columns=len(ZRAM_ALGORITHMS))).set_buttons(
            self.zram_algorithm_buttons.values()
        )
        self.zram_note = card.add(muted_label())

    def build_zswap_card(self):
        card = self.add(Card("zswap"))
        self.zswap_row = card.add(InfoRow("zswap"))
        self.zswap_toggle = card.add(ToggleRow("Enable zswap", ZSWAP_ABOUT))
        self.zswap_toggle.toggled.connect(self.save_zswap)

    def on_activate(self):
        self.memory_saving = None
        self.swap_saving = None
        self.refresh_status(callback=lambda r: self.notify(r, quiet=True))
        self.call("get_gpu_memory", callback=self._memory_loaded)
        self.call("get_swap_settings", callback=self._swap_loaded)

    def on_status(self, result):
        if result["success"]:
            self.status = result["data"]
            self.status_error = None
        else:
            self.status_error = result["error"]
        self.render_status()

    def _memory_loaded(self, result):
        if result["success"]:
            self.memory = result["data"]
            self._fill_custom_vram()
        self.notify(result, quiet=True)
        self.render_memory()

    def _swap_loaded(self, result):
        if result["success"]:
            self.swap = result["data"]
        self.notify(result, quiet=True)
        self.render_swap()

    def _fill_custom_vram(self):
        configured = self.memory["vram_configured"]
        if configured // MIB not in self.vram_buttons and configured >= TOO_SMALL_VRAM:
            self.vram_input.setText(f"{configured / GIB:.2f}".rstrip("0").rstrip("."))

    def _custom_vram_mb(self):
        try:
            gigabytes = float(self.vram_input.text().strip().replace(",", "."))
        except ValueError:
            return None
        if not CUSTOM_VRAM_MIN_GB <= gigabytes <= CUSTOM_VRAM_MAX_GB:
            return None
        return round(gigabytes * 1024)

    def save_vram(self, megabytes):
        self.save_memory("set_vram", megabytes)

    def save_custom_vram(self):
        megabytes = self._custom_vram_mb()
        if megabytes is not None:
            self.memory_saving = ("set_vram", "custom")
            self._save(self.memory_saving, "set_vram", megabytes)

    def save_memory(self, method, value):
        self.memory_saving = (method, value)
        self._save(self.memory_saving, method, value)

    def _save(self, saving, method, value):
        self.render_memory()

        def done(result):
            if result["success"]:
                self.memory = result["data"]
            self.notify(result)
            self.memory_saving = None
            self.render_memory()

        self.call(method, value, callback=done)

    def save_zram(self, enabled=None, size=None, algorithm=None):
        swap = self.swap
        if enabled is None:
            enabled = True
        if size is None:
            size = swap["zram_size"] if swap["zram_size"] in self.zram_size_buttons else None
        if algorithm is None:
            current = swap["zram_algorithm"]
            algorithm = current if current in self.zram_algorithm_buttons else None
        size = size or DEFAULT_ZRAM_SIZE
        algorithm = algorithm or DEFAULT_ZRAM_ALGORITHM
        self.swap_saving = ("zram", enabled, size, algorithm)
        self.render_swap()

        def done(result):
            if result["success"]:
                self.swap = result["data"]
            self.notify(result)
            self.swap_saving = None
            self.render_swap()

        self.call("set_zram", enabled, size, algorithm, callback=done)

    def save_zswap(self, checked):
        self.swap_saving = ("zswap", checked)
        self.render_swap()

        def done(result):
            if result["success"]:
                self.swap = result["data"]
            self.notify(result)
            self.swap_saving = None
            self.render_swap()
            self.refresh_status()

        self.call("set_zswap", checked, callback=done)

    def render(self):
        self.render_status()
        self.render_memory()
        self.render_swap()

    def render_status(self):
        status = self.status
        if status is None:
            error = self.status_error
            self.ram_row.set("Unknown" if error else "…", error, error=bool(error))
            self.swap_row.set("Unknown" if error else "…")
        else:
            total, available = status["ram_total"], status["ram_available"]
            if total and available is not None:
                self.ram_row.set(
                    f"{format_usage(total - available)} of {format_usage(total)}",
                    f"{format_usage(available)} available",
                )
            else:
                self.ram_row.set("Unknown")
            self._render_swap_row(status)
        self.render_swap()

    def _render_swap_row(self, status):
        swaps = status["swaps"]
        if not swaps:
            self.swap_row.set("None", "No swap is active.")
            return
        total = status["swap_total"] or sum(swap["size"] for swap in swaps)
        free = status["swap_free"]
        used = total - free if free is not None else sum(swap["used"] for swap in swaps)
        devices = []
        for swap in swaps:
            kind = "zram" if "zram" in swap["name"] else swap["type"]
            devices.append(
                f"{swap['name']} ({kind}): {format_usage(swap['used'])} of "
                f"{format_usage(swap['size'])}"
            )
        self.swap_row.set(f"{format_usage(used)} of {format_usage(total)}", "\n".join(devices))

    def render_memory(self):
        memory = self.memory
        ready = bool(memory and memory["boot_ready"])
        enabled = ready and self.memory_saving is None
        if memory is None:
            self.vram_row.set("…")
            self.gtt_row.set("…")
        else:
            self._render_vram_row(memory, ready)
            self._render_gtt_row(memory, ready)

        configured = memory["vram_configured"] if memory else None
        for megabytes, button in self.vram_buttons.items():
            button.setEnabled(enabled)
            button.set_selected(configured == megabytes * MIB)
            button.set_busy(self.memory_saving == ("set_vram", megabytes))
        self.vram_input.setEnabled(enabled)
        custom = self._custom_vram_mb()
        self.vram_custom_button.setEnabled(
            enabled and custom is not None and custom * MIB != configured
        )
        busy = self.memory_saving == ("set_vram", "custom")
        self.vram_custom_button.setText("Applying…" if busy else "Set")
        pages = memory["gtt_pages"] if memory else None
        for gigabytes, button in self.gtt_buttons.items():
            wanted = gigabytes * MIB // 4 if gigabytes else None
            button.setEnabled(enabled)
            button.set_selected(memory is not None and pages == wanted)
            button.set_busy(self.memory_saving == ("set_gtt_limit", gigabytes))

    def _render_vram_row(self, memory, ready):
        running = memory["vram_running"]
        configured = memory["vram_configured"]
        value = format_bytes(running) if running is not None else "Unknown"
        if not ready:
            self.vram_row.set(value, memory["boot_error"])
        elif configured < TOO_SMALL_VRAM:
            self.vram_row.set(
                value,
                f"vram.txt asks for {format_bytes(configured)}, which can cause a black screen. "
                "It's read as hex, so it was probably written in decimal. Pick a size below.",
                error=True,
            )
        elif running is not None and abs(running - configured) > configured / 16:
            self.vram_row.set(value, f"{format_bytes(configured)} after a reboot")
        else:
            self.vram_row.set(value)

    def _render_gtt_row(self, memory, ready):
        pages = memory["gtt_pages"]
        value = "Default" if pages is None else format_bytes(pages * 4096)
        pending = ready and memory["gtt_pending"]
        self.gtt_row.set(value, "Takes effect after a reboot" if pending else None)

    def render_swap(self):
        self._render_zram()
        self._render_zswap()

    def _render_zram(self):
        swap = self.swap
        status = self.status
        running = status["zram"] if status else None
        if running:
            parts = [running["algorithm"] or "Unknown compression"]
            if running["original"] is not None and running["compressed"] is not None:
                parts.append(
                    f"{format_usage(running['original'])} stored in "
                    f"{format_usage(running['compressed'])}"
                )
            value = format_usage(running["disksize"])
        else:
            parts = []
            value = "…" if status is None else "Off"
        if swap and swap["zram_pending"]:
            parts.append("Your change takes effect after a reboot")
        self.zram_row.set(value, " · ".join(parts) or None)

        saving = self.swap_saving
        zram_saving = saving if saving and saving[0] == "zram" else None
        configured = swap is not None and swap["zram_enabled"]
        self.zram_toggle.set_checked(zram_saving[1] if zram_saving else configured)
        self.zram_toggle.setEnabled(swap is not None and saving is None)
        options = configured and saving is None
        for size, button in self.zram_size_buttons.items():
            button.setEnabled(options)
            button.set_selected(configured and swap["zram_size"] == size)
            button.set_busy(bool(zram_saving and zram_saving[1] and zram_saving[2] == size))
        for algorithm, button in self.zram_algorithm_buttons.items():
            button.setEnabled(options)
            button.set_selected(configured and swap["zram_algorithm"] == algorithm)
            button.set_busy(bool(zram_saving and zram_saving[1] and zram_saving[3] == algorithm))

        notes = []
        if swap is not None:
            if swap["zram_error"]:
                notes.append(swap["zram_error"])
            elif not swap["zram_generator"]:
                notes.append(
                    "zram-generator isn't installed. Install it with your package manager to "
                    "turn zram on here."
                )
            if configured and swap["zram_size"] not in self.zram_size_buttons:
                notes.append(f"Configured size: {swap['zram_size'] or 'zram-generator default'}.")
            if swap["zram_source"] and swap["zram_source"].startswith(("/usr", "/lib")):
                notes.append(f"Using your distro's default from {swap['zram_source']}.")
        self.zram_note.setText(" ".join(notes))
        self.zram_note.setVisible(bool(notes))

    def _render_zswap(self):
        status = self.status
        swap = self.swap
        zswap = status["zswap"] if status else None
        if status is None:
            self.zswap_row.set("…")
        elif zswap is None:
            self.zswap_row.set("Unavailable", "This kernel doesn't include zswap.")
        else:
            parts = []
            if zswap["compressor"]:
                parts.append(zswap["compressor"])
            if zswap["max_pool_percent"] is not None:
                parts.append(f"up to {zswap['max_pool_percent']}% of RAM")
            configured = swap["zswap_configured"] if swap else None
            if swap and not swap["boot_ready"]:
                parts.append("Changes last until reboot: the boot partition wasn't found")
            elif configured is not None and configured != zswap["enabled"]:
                parts.append(f"{'On' if configured else 'Off'} after a reboot")
            if zswap["enabled"] and status["zram"]:
                parts.append("zram is also on, so pages are compressed twice")
            self.zswap_row.set("On" if zswap["enabled"] else "Off", " · ".join(parts) or None)

        saving = self.swap_saving
        if saving and saving[0] == "zswap":
            self.zswap_toggle.set_checked(saving[1])
        else:
            self.zswap_toggle.set_checked(bool(zswap and zswap["enabled"]))
        self.zswap_toggle.setEnabled(zswap is not None and saving is None)
