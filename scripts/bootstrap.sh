#!/usr/bin/env bash
# OpenDIHM Firmware Production Bootstrapper
# Optimized for Raspberry Pi Zero 2 W (512MB RAM)
# This script handles swap creation, system dependencies, and environment setup.

set -euo pipefail

# Configuration
PROJECT_DIR="/opt/opendihm"
SERVICE_USER="opendihm"
SERVICE_GROUP="opendihm"
LOG_FILE="/tmp/opendihm_bootstrap.log"

# Argument Parsing for Debug Mode
DEBUG_MODE=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --debug|-d) DEBUG_MODE=true ;;
    esac
    shift
done

# Export non-interactive flag for apt
export DEBIAN_FRONTEND=noninteractive

# Log everything to file and terminal
exec > >(tee -i "$LOG_FILE") 2>&1

echo "=========================================="
echo "    OpenDIHM Firmware Bootstrapper"
echo "=========================================="
echo "[*] Started at: $(date)"
echo "[*] Logging to: $LOG_FILE"

# 1. Authority Check
if ! sudo -n true && [ "$EUID" -ne 0 ]; then
    echo "[!] This script needs sudo privileges. Please authenticate."
    sudo -v
fi

# 2. Memory Optimization: Add Swap Space
# Pi Zero 2W only has 512MB RAM. uv and compilers need more.
echo "[*] Checking for swap space..."
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
    if [ ! -f /swapfile ]; then
        echo "[*] Creating 1GB swap file to prevent OOM crashes..."
        sudo fallocate -l 1G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
    fi
    echo "[*] Enabling swap..."
    sudo swapon /swapfile
else
    echo "[*] Swap space is already active."
fi

# 3. UV Toolchain Management
echo "[*] Checking 'uv' installation..."
if ! command -v uv &> /dev/null; then
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "[*] Installing Astral 'uv' toolchain (Rate-limited to 500kB/s)..."
        mkdir -p "$HOME/.local/bin"
        # Download the specific release for Pi 64-bit with a rate limit
        wget --limit-rate=500k -qO /tmp/uv.tar.gz https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-unknown-linux-gnu.tar.gz
        tar -xzf /tmp/uv.tar.gz -C /tmp
        mv /tmp/uv-aarch64-unknown-linux-gnu/uv "$HOME/.local/bin/uv"
        mv /tmp/uv-aarch64-unknown-linux-gnu/uvx "$HOME/.local/bin/uvx"
        rm -rf /tmp/uv.tar.gz /tmp/uv-aarch64-unknown-linux-gnu
        chmod +x "$HOME/.local/bin/uv" "$HOME/.local/bin/uvx"
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi
echo "[*] Using $(uv --version)"

# 4. Security: Service User
echo "[*] Ensuring dedicated system user '$SERVICE_USER' exists..."
if ! id "$SERVICE_USER" &>/dev/null; then
    sudo useradd -r -s /usr/sbin/nologin "$SERVICE_USER"
    echo "[*] Created system user: $SERVICE_USER"
fi

# Add user to hardware groups
for hardware_group in gpio video input dialout; do
    if getent group "$hardware_group" &>/dev/null; then
        sudo usermod -aG "$hardware_group" "$SERVICE_USER" || true
    fi
done

# 5. System Dependencies
echo "[*] Installing required system libraries..."
sudo apt-get update -qq
sudo apt-get install -y -qq swig liblgpio-dev python3-dev build-essential libopenblas-dev

# 6. Environment Setup
if [ ! -d "$PROJECT_DIR" ]; then
    echo "[!] CRITICAL: Project directory $PROJECT_DIR not found."
    exit 1
fi

cd "$PROJECT_DIR"

echo "[*] Initializing virtual environment..."

# Memory Constraints for 512MB RAM using uv's official Environment Variables
export UV_CONCURRENT_DOWNLOADS=1
export UV_CONCURRENT_BUILDS=1
export UV_NO_PROGRESS=1
export UV_PYTHON_DOWNLOADS=never

# Use piwheels for faster, pre-built binaries on ARM architecture
# We explicitly use piwheels as the primary index to avoid time-consuming and memory-intensive builds
# -q hides the list of installed packages to keep the console clean
UV_INSTALL_OPTS="-q --index-url https://www.piwheels.org/simple --extra-index-url https://pypi.org/simple"

if [ ! -d ".venv" ]; then
    echo "[*] Using system Python to avoid large downloads..."
    uv venv --python /usr/bin/python3
fi
source .venv/bin/activate

echo "[*] Installing Python packages..."

if [ "$DEBUG_MODE" = true ]; then
    echo "[*] Mode: DEVELOPMENT (Editable + [dev] dependencies)"
    uv pip install $UV_INSTALL_OPTS -e ".[dev]"
else
    uv pip install $UV_INSTALL_OPTS .
fi

# 7. Service Installation
SERVICE_UNIT="$PROJECT_DIR/systemd/opendihm-firmware.service"
if [ -f "$SERVICE_UNIT" ]; then
    echo "[*] Installing systemd unit file..."
    sudo cp "$SERVICE_UNIT" /etc/systemd/system/
    sudo systemctl daemon-reload
fi

# 8. Ownership & Permissions
echo "[*] Securing file permissions..."
sudo chown -R $USER:$SERVICE_GROUP "$PROJECT_DIR"
# Allow group (service) write access so lgpio can create its .lgd-nfyX named pipes
find "$PROJECT_DIR" -type d -exec sudo chmod 770 {} +
find "$PROJECT_DIR" -type f -exec sudo chmod 660 {} +
find "$PROJECT_DIR/scripts" -type f -name "*.sh" -exec sudo chmod 770 {} +
sudo chmod -R 770 ".venv/bin"

echo "=========================================="
echo "[*] Bootstrap sequence complete!"
echo "[*] Access the full log at: $LOG_FILE"
echo ""
echo "    Service Management Commands:"
echo "    - Status:  sudo systemctl status opendihm-firmware"
echo "    - Start:   sudo systemctl start opendihm-firmware"
echo "    - Logs:    journalctl -u opendihm-firmware -f"
echo "=========================================="
