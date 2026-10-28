#!/usr/bin/env bash

set -euo pipefail

APP_NAME="ps5-hwcon-gui"
PREFIX="/opt/ps5-hwcon-gui"
BIN_LINK="/usr/local/bin/ps5-hwcon-gui"
DESKTOP_FILE="/usr/local/share/applications/ps5-hwcon-gui.desktop"
SERVICE_NAME="ps5-hwcon"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
SETTINGS_DIR="/var/lib/ps5-hwcon"
MIN_PYTHON="3.9"
REPO="NotHavocc/ps5-hwcon-gui"
REF="main"

SRC_DIR=""
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [ -n "$SCRIPT_PATH" ] && [ -f "$(dirname -- "$SCRIPT_PATH")/pyproject.toml" ]; then
  SRC_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"
fi

FORCE=0
UNINSTALL=0
SERVICE=0

usage() {
  cat <<EOF
Usage: $0 [options]

  --service      Also install and start the headless service, which restores your
                 settings at boot and runs Thermal Guard and LED loops without a window
  --force        Install even if the PS5 kernel interfaces are missing
  --uninstall    Remove the app (your settings in $SETTINGS_DIR are kept)
  --ref NAME     Branch or tag to download when not run from a copy of the repo
                 (default: $REF)
  -h, --help     Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICE=1; shift ;;
    --force) FORCE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --ref)
      [ $# -ge 2 ] || { echo "--ref needs a branch or tag name" >&2; exit 2; }
      REF="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  BOLD=$'\e[1m'; RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
else
  BOLD=""; RED=""; GREEN=""; YELLOW=""; RESET=""
fi
step() { printf '%s==>%s %s\n' "$BOLD" "$RESET" "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die()  { printf '%s  ✗ %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "This installer is for Linux (the PS5). On other systems see the README."
if [ "$(id -u)" -eq 0 ]; then
  die "Run this as your normal user, not root. It asks for sudo when it needs it."
fi
command -v sudo >/dev/null || die "sudo is required"

have_systemd() { command -v systemctl >/dev/null && [ -d /run/systemd/system ]; }

stop_service() {
  if have_systemd && systemctl list-unit-files "$SERVICE_NAME.service" >/dev/null 2>&1 \
    && systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl stop "$SERVICE_NAME"
    return 0
  fi
  return 1
}

if [ "$UNINSTALL" -eq 1 ]; then
  step "Removing PS5 Hardware Control"
  if have_systemd && [ -f "$SERVICE_FILE" ]; then
    sudo systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
    sudo rm -f -- "$SERVICE_FILE"
    sudo systemctl daemon-reload
    ok "Service removed"
  fi
  sudo rm -rf -- "$PREFIX"
  sudo rm -f -- "$BIN_LINK" "$DESKTOP_FILE"
  ok "App removed (settings in $SETTINGS_DIR are kept)"
  exit 0
fi

if [ -z "$SRC_DIR" ]; then
  step "Downloading $REPO ($REF)"
  command -v curl >/dev/null || die "curl is required"
  command -v tar >/dev/null || die "tar is required"
  DOWNLOAD_DIR="$(mktemp -d)"
  trap 'rm -rf -- "$DOWNLOAD_DIR"' EXIT
  if ! curl -fsSL "https://github.com/$REPO/archive/$REF.tar.gz" \
    | tar -xzf - -C "$DOWNLOAD_DIR" --strip-components=1; then
    die "Downloading https://github.com/$REPO/archive/$REF.tar.gz failed"
  fi
  SRC_DIR="$DOWNLOAD_DIR"
  ok "Downloaded"
fi

for file in pyproject.toml ps5hwcon/__main__.py ps5hwcon/icon.png packaging/ps5-hwcon.service; do
  [ -f "$SRC_DIR/$file" ] || die "$file is missing from $SRC_DIR. Is this the right repository?"
done

step "Checking Python"
PYTHON="$(command -v python3 || true)"
[ -n "$PYTHON" ] || die "python3 is not installed. Install it with your package manager, then rerun this script."
if ! "$PYTHON" -c "import sys; sys.exit(sys.version_info < tuple(map(int, '$MIN_PYTHON'.split('.'))))"; then
  die "Python $MIN_PYTHON or newer is needed, found $("$PYTHON" -V 2>&1)"
fi
if ! "$PYTHON" -c "import venv, ensurepip" 2>/dev/null; then
  hint="Install the Python venv module"
  command -v apt-get >/dev/null && hint="$hint: sudo apt install python3-venv"
  command -v pacman >/dev/null && hint="$hint (it is part of the python package on Arch)"
  die "$hint, then rerun this script."
fi
ok "$("$PYTHON" -V 2>&1) at $PYTHON"

step "Checking PS5 kernel interfaces"
missing=0
for path in /sys/bus/platform/devices/ps5-fan/target_temp /sys/class/misc/ps5_buzzer/beep \
  /sys/devices/system/cpu/cpufreq /sys/class/devfreq/ps5-gpufreq; do
  if [ -e "$path" ]; then ok "$path"; else warn "missing: $path"; missing=1; fi
done
led_nodes=(/sys/class/leds/ps5:*)
if [ -e "${led_nodes[0]}" ]; then ok "/sys/class/leds/ps5:*"; else warn "missing: /sys/class/leds/ps5:*"; missing=1; fi
if [ "$missing" -eq 1 ]; then
  if [ "$FORCE" -eq 1 ]; then
    warn "Continuing because of --force. Missing parts won't work until the ps5-linux-patches kernel is running."
  else
    die "Some interfaces are missing (uname -r: $(uname -r)). Boot the ps5-linux-patches kernel first, or pass --force."
  fi
fi

was_running=0
if stop_service; then
  was_running=1
  ok "Stopped the running $SERVICE_NAME service"
fi

step "Copying the app to $PREFIX"
sudo mkdir -p "$PREFIX"
sudo rm -rf -- "$PREFIX/src"
sudo mkdir -p "$PREFIX/src"
(cd "$SRC_DIR" && tar -cf - --exclude='__pycache__' --exclude='*.egg-info' \
  pyproject.toml README.md LICENSE ps5hwcon packaging) | sudo tar -xf - -C "$PREFIX/src"
ok "Source copied"

step "Installing PyQt6 into a private environment (this downloads about 100 MB)"
if [ ! -x "$PREFIX/.venv/bin/python" ]; then
  sudo "$PYTHON" -m venv "$PREFIX/.venv"
fi
sudo "$PREFIX/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$PREFIX/src"
ok "Installed into $PREFIX/.venv"

step "Checking that Qt starts"
if ! qt_error="$(sudo env QT_QPA_PLATFORM=offscreen "$PREFIX/.venv/bin/python" -c \
  "from PyQt6.QtWidgets import QApplication; QApplication([])" 2>&1)"; then
  printf '%s\n' "$qt_error" >&2
  die "Qt could not start. A system graphics library is probably missing (see the error above)."
fi
ok "Qt works"
has_xcb_cursor() { ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor\.so\.0'; }
PATH="$PATH:/sbin:/usr/sbin"
if command -v ldconfig >/dev/null && ! has_xcb_cursor; then
  step "Installing libxcb-cursor (Qt needs it in X11 sessions)"
  if command -v apt-get >/dev/null; then
    sudo apt-get install -y libxcb-cursor0 || true
  elif command -v dnf >/dev/null; then
    sudo dnf install -y xcb-util-cursor || true
  elif command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm xcb-util-cursor || true
  fi
  if has_xcb_cursor; then
    ok "libxcb-cursor installed"
  else
    warn "libxcb-cursor is still missing. The window won't open in X11 sessions until you install it" \
      "(Debian/Ubuntu: libxcb-cursor0, Fedora/Arch: xcb-util-cursor)."
  fi
fi

step "Adding the launcher and menu entry"
sudo mkdir -p "$(dirname "$BIN_LINK")" "$(dirname "$DESKTOP_FILE")"
sudo tee "$BIN_LINK" >/dev/null <<EOF
#!/bin/sh
APP="$PREFIX/.venv/bin/$APP_NAME"
if [ "\$(id -u)" -eq 0 ]; then
  exec "\$APP" "\$@"
fi
if [ -t 0 ] && command -v sudo >/dev/null; then
  exec sudo -E "\$APP" "\$@"
fi
exec pkexec env DISPLAY="\$DISPLAY" WAYLAND_DISPLAY="\$WAYLAND_DISPLAY" \\
  XAUTHORITY="\${XAUTHORITY:-\$HOME/.Xauthority}" XDG_RUNTIME_DIR="\$XDG_RUNTIME_DIR" \\
  XDG_SESSION_TYPE="\$XDG_SESSION_TYPE" "\$APP" "\$@"
EOF
sudo chmod 755 "$BIN_LINK"
sudo tee "$DESKTOP_FILE" >/dev/null <<EOF
[Desktop Entry]
Type=Application
Name=PS5 Hardware Control
Comment=Fan, CPU/GPU clocks and LED control for PS5 Linux
Exec=$BIN_LINK
Icon=$PREFIX/src/ps5hwcon/icon.png
Terminal=false
Categories=System;Settings;HardwareSettings;
EOF
ok "Run it with: $BIN_LINK  (or PS5 Hardware Control in the app menu)"

if [ "$SERVICE" -eq 1 ] || [ "$was_running" -eq 1 ]; then
  step "Installing the headless service"
  have_systemd || die "systemd is not running, so the service can't be installed"
  sed "s|^ExecStart=.*|ExecStart=$PREFIX/.venv/bin/$APP_NAME --headless|" \
    "$PREFIX/src/packaging/ps5-hwcon.service" | sudo tee "$SERVICE_FILE" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "$SERVICE_NAME is running and starts at boot"
    warn "Stop it before opening the window: sudo systemctl stop $SERVICE_NAME"
  else
    warn "The service didn't start. Check: journalctl -u $SERVICE_NAME"
  fi
fi

printf '\n%sDone.%s Start PS5 Hardware Control from the app menu, or run %s\n' "$BOLD" "$RESET" "$BIN_LINK"
