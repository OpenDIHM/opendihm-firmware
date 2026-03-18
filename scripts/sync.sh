#!/usr/bin/env bash

# Sync script for OpenDIHM firmware
# Syncs current workspace to the Raspberry Pi

set -euo pipefail

SERVER_NAME="${1}"

if [ -z "${SERVER_NAME}" ]; then
    echo "Usage: $0 <server_name>"
    exit 1
fi

DEST="${SERVER_NAME}:~/opendihm-firmware/"
SRC="$(dirname "$0")/../"

echo "Syncing ${SRC} to ${DEST}..."

rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.mypy_cache' --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude 'logs' "$SRC" "$DEST"

echo "Sync complete!"
