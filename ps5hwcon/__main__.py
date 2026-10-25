import argparse
import asyncio
import logging
import signal
import sys

from . import backend


def run_headless():
    """Restore saved settings and run Thermal Guard and the LED loop without a window."""

    async def main():
        service = backend.Backend()
        await service.start()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
        await stop.wait()
        await service.stop()

    asyncio.run(main())
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ps5-hwcon-gui",
        description="PS5 Linux fan, CPU/GPU clock and LED control.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run without a window: restore saved settings, then keep Thermal Guard, "
        "Overheat Alarm and LED loops running (for the systemd service)",
    )
    parser.add_argument(
        "--tray", action="store_true", help="start hidden in the system tray"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log debug messages")
    args, qt_args = parser.parse_known_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    lock = backend.acquire_instance_lock()
    if lock is None:
        message = (
            "Another PS5 Hardware Control instance (the GUI or the headless service) is already "
            f"running for {backend.SETTINGS_DIR}. Stop it first, e.g. "
            "'sudo systemctl stop ps5-hwcon'."
        )
        if args.headless:
            print(message, file=sys.stderr)
            return 1
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication(sys.argv[:1] + qt_args)
        QMessageBox.critical(None, "PS5 Hardware Control", message)
        return 1

    if args.headless:
        return run_headless()

    from .app import run_gui

    return run_gui(sys.argv[:1] + qt_args, start_hidden=args.tray)


if __name__ == "__main__":
    sys.exit(main())
