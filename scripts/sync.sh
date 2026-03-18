#!/usr/bin/env bash
# OpenDIHM Firmware Sync Script
# Syncs current workspace to the Raspberry Pi, handling SSH keys and directory provisioning.

set -euo pipefail

# Configuration
SRC="$(cd "$(dirname "$0")/.." && pwd)/"
DEST_DIR="/opt/opendihm"

# Argument Parsing
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <user@server_name>"
    echo "Example: $0 admin@opendihm"
    exit 1
fi

SERVER_NAME="${1}"
DEST="${SERVER_NAME}:${DEST_DIR}/"

echo "=========================================="
echo "    OpenDIHM Firmware Sync Tool"
echo "=========================================="
echo "[*] Source: $SRC"
echo "[*] Target: $DEST"

# 1. SSH Key Exchange Setup (Passwordless Authentication)
echo "[*] Checking SSH connectivity and authentication..."
# We test SSH with BatchMode=yes. If it fails, keys are missing.
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SERVER_NAME" exit &>/dev/null; then
    echo "[!] Passwordless SSH not configured or host unreachable."
    echo "[*] Attempting to share SSH keys using ssh-copy-id..."
    
    # Generate an SSH key if the user doesn't have one
    if [ ! -f "$HOME/.ssh/id_rsa" ] && [ ! -f "$HOME/.ssh/id_ed25519" ]; then
        echo "[*] No SSH key found. Generating an ED25519 keypair..."
        ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519" -N "" -q
    fi

    # Copy the key to the target
    ssh-copy-id "$SERVER_NAME" || {
        echo "[!] Failed to copy SSH key. Please verify the host and password."
        exit 1
    }
    echo "[*] SSH key shared successfully. Future logins will be passwordless."
else
    echo "[*] Passwordless SSH is active."
fi

# 2. Remote Provisioning (Create /opt/opendihm)
echo "[*] Verifying remote project directory structure..."
# We use sudo to create the directory if it doesn't exist, and change ownership to the login user
# We only run the commands if the directory is missing, to avoid unnecessary sudo prompts
ssh "$SERVER_NAME" "if [ ! -d '${DEST_DIR}' ]; then
    echo '    -> Creating ${DEST_DIR}...'
    sudo mkdir -p '${DEST_DIR}'
    sudo chown -R \$USER '${DEST_DIR}'
    sudo chmod 750 '${DEST_DIR}'
fi"

# 3. Code Synchronization
echo "[*] Synchronizing workspace via rsync..."

EXCLUDES=(
    .git
    .venv
    __pycache__
    .mypy_cache
    .pytest_cache
    .ruff_cache
    logs
    .DS_Store
)

# Build rsync exclude options
RSYNC_EXCLUDES=()
for exclude in "${EXCLUDES[@]}"; do
    RSYNC_EXCLUDES+=(--exclude "$exclude")
done

# Perform the sync
rsync -avz --delete "${RSYNC_EXCLUDES[@]}" "$SRC" "$DEST"

echo "=========================================="
echo "[*] Sync complete successfully!"
echo "=========================================="
