#!/usr/bin/env bash
# Builds dist/ps5-hwcon-gui, a single executable with Python and Qt bundled.
# Must run on Linux x86_64 (the PS5's architecture); GitHub Actions does this on release.
#
#   python3 -m venv .venv && .venv/bin/pip install . "pyinstaller>=6.10,<7"
#   PATH="$PWD/.venv/bin:$PATH" packaging/build_binary.sh

set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name ps5-hwcon-gui \
  --paths . \
  --add-data "ps5hwcon/icon.png:ps5hwcon" \
  --add-data "ps5hwcon/check.svg:ps5hwcon" \
  --exclude-module tkinter \
  packaging/pyinstaller_entry.py

echo "Built dist/ps5-hwcon-gui"
