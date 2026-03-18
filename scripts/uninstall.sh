#!/usr/bin/env bash
# OpenDIHM Firmware Uninstaller
# This script completely uninstalls the OpenDIHM Firmware from the Raspberry Pi.
# It undoes all actions performed by bootstrap_pi.sh.

set -euo pipefail

# Configuration
PROJECT_DIR="/opt/opendihm"
SERVICE_USER="opendihm"
SERVICE_UNIT="opendihm-firmware.service"
SWAP_FILE="/swapfile"
LOG_FILE="/tmp/opendihm_uninstall.log"

export DEBIAN_FRONTEND=noninteractive
exec > >(tee -i "$LOG_FILE") 2>&1

echo "=========================================="
echo "    OpenDIHM Firmware Uninstaller"
echo "=========================================="
echo "[*] Started at: $(date)"
echo "[*] Logging to: $LOG_FILE"

# 1. Authority Check
if ! sudo -n true && [ "$EUID" -ne 0 ]; then
    echo "[!] This script needs sudo privileges. Please authenticate."
    sudo -v
fi

# 2. Stop and Remove Systemd Service
echo "[*] Stopping and removing systemd service..."
if systemctl is-active --quiet "$SERVICE_UNIT"; then
    sudo systemctl stop "$SERVICE_UNIT"
fi
if systemctl is-enabled --quiet "$SERVICE_UNIT"; then
    sudo systemctl disable "$SERVICE_UNIT"
fi
if [ -f "/etc/systemd/system/$SERVICE_UNIT" ]; then
    sudo rm "/etc/systemd/system/$SERVICE_UNIT"
    sudo systemctl daemon-reload
    echo "[*] Systemd service $SERVICE_UNIT removed."
else
    echo "[*] Systemd service not found. Skipping."
fi

# 3. Remove Service User
echo "[*] Removing dedicated system user '$SERVICE_USER'..."
if id "$SERVICE_USER" &>/dev/null; then
    # -f forces removal even if logged in
    sudo userdel -f "$SERVICE_USER" || true
    echo "[*] System user '$SERVICE_USER' removed."
else
    echo "[*] User '$SERVICE_USER' does not exist."
fi

# 4. Remove Project Files
echo "[*] Removing project directory..."
if [ -d "$PROJECT_DIR" ]; then
    sudo rm -rf "$PROJECT_DIR"
    echo "[*] Project directory $PROJECT_DIR removed."
else
    echo "[*] Project directory $PROJECT_DIR not found. Skipping."
fi

# 5. Remove System Dependencies
# Note: build-essential is typically kept, but we remove the specific libraries
DEPENDENCIES="swig liblgpio-dev python3-dev libopenblas-dev"
echo "[*] Removing previously installed APT dependencies..."
sudo apt-get remove -y -qq $DEPENDENCIES || true
sudo apt-get autoremove -y -qq || true

# 6. Remove Swap File
echo "[*] Checking for created swap file..."
if [ -f "$SWAP_FILE" ]; then
    echo "[*] Disabling and removing $SWAP_FILE..."
    sudo swapoff "$SWAP_FILE" || true
    sudo rm -f "$SWAP_FILE"
    # Remove swapfile entry from /etc/fstab safely
    sudo sed -i '\|/swapfile none swap sw 0 0|d' /etc/fstab
    echo "[*] Swap file removed."
else
    echo "[*] Swap file not found. Skipping."
fi

# 7. Remove uv Toolchain
echo "[*] Removing uv toolchain..."
if [ -x "$HOME/.local/bin/uv" ]; then
    rm -f "$HOME/.local/bin/uv"
    rm -f "$HOME/.local/bin/uvx"
    echo "[*] uv removed from ~/.local/bin/."
else
    echo "[*] uv not found in ~/.local/bin/. Skipping."
fi

echo "=========================================="
echo "[*] Uninstall sequence complete!"
echo "[*] OpenDIHM Firmware has been removed."
echo "=========================================="
