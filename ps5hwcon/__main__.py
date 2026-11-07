import argparse
import logging
import sys

from . import backend


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ps5-hwcon-gui",
        description="PS5 Linux fan, CPU/GPU clock, memory and LED control.",
    )
    parser.add_argument(
        "--tray", action="store_true", help="start hidden in the system tray"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log debug messages")
    parser.add_argument("--tray-helper", type=int, metavar="WAIT_MS", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.tray_helper is not None:
        from .tray import run_helper

        return run_helper(args.tray_helper)

    lock = backend.acquire_instance_lock()
    if lock is None:
        message = (
            f"PS5 Hardware Control is already running for {backend.SETTINGS_DIR}. "
            "Check the system tray."
        )
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication(sys.argv[:1] + qt_args)
        QMessageBox.critical(None, "PS5 Hardware Control", message)
        return 1

    from .app import run_gui

    return run_gui(sys.argv[:1] + qt_args, start_hidden=args.tray)


if __name__ == "__main__":
    sys.exit(main())
