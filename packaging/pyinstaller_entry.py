"""Entry point for the single-file PyInstaller build (see packaging/build_binary.sh)."""

import sys

from ps5hwcon.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
