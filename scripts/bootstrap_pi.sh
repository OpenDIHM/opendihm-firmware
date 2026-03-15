#!/usr/bin/env bash
# OpenDIHM Firmware Bootstrap Script for Raspberry Pi

set -e

echo "=== OpenDIHM Firmware Bootstrapper ==="

echo "[*] Checking if 'uv' is installed..."
if ! command -v uv &> /dev/null; then
    # In some cases ~/.local/bin might be added but not in current PATH
    if [ -x "$HOME/.local/bin/uv" ]; then
        echo "[*] 'uv' found in ~/.local/bin but not in PATH. Adding it."
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "[*] 'uv' not found. Installing the Astral 'uv' toolchain..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        echo "[*] 'uv' installed successfully."
    fi
else
    echo "[*] 'uv' is already installed: $(uv --version)"
fi

echo "[*] Setting up the OpenDIHM Firmware environment..."

# Navigate to the project directory synced by sync.sh
if [ ! -d "$HOME/opendihm-firmware" ]; then
    echo "Directory $HOME/opendihm-firmware not found!"
    echo "Please run ./scripts/sync.sh from your host machine first."
    exit 1
fi

cd "$HOME/opendihm-firmware"

echo "[*] Creating virtual environment and installing dependencies..."
# Create a venv, download Python 3.11 if missing via uv, and install packages
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

echo "======================================"
echo "[*] Bootstrap sequence complete!"
echo "[*] You can now start the firmware API server on the Raspberry Pi:"
echo ""
echo "    cd ~/opendihm-firmware"
echo "    uv run uvicorn opendihm_firmware.app:app --host 0.0.0.0 --port 8000"
echo "======================================"
