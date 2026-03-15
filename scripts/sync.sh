#!/usr/bin/env bash

# Sync script for OpenDIHM firmware
# Syncs current workspace to the Raspberry Pi (localserver)

set -euo pipefail

DEST="localserver:~/opendihm-firmware/"
SRC="$(dirname "$0")/../"

echo "Syncing ${SRC} to ${DEST}..."

rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.mypy_cache' --exclude '.pytest_cache' --exclude 'logs' "$SRC" "$DEST"

echo "Sync complete!"
