#!/usr/bin/env bash

# OpenDIHM Firmware - Stream Viewer Utility
# 
# Automatically connects to the Raspberry Pi over SSH to fetch its real network IP,
# triggers the live preview stream, boots ffplay to display it natively,
# and shuts down the stream cleanly when the video window is closed.

set -e

SSH_HOST="${1:-localserver}"
API_PORT="${2:-8000}"
PREVIEW_PORT="${3:-8888}"

echo "[*] Connecting to $SSH_HOST to retrieve real network IP..."
PI_IP=$(ssh -o ConnectTimeout=5 "$SSH_HOST" "hostname -I" | awk '{print $1}')

if [ -z "$PI_IP" ]; then
    echo "[!] Error: Could not determine the IP address for $SSH_HOST over SSH."
    exit 1
fi

echo "[*] Target IP acquired: $PI_IP"

# Clean-up function that runs when the script or ffplay is closed/interrupted
cleanup() {
    echo ""
    echo "[*] Cleaning up: Sending HTTP kill command to camera stream..."
    curl -s -X POST "http://$PI_IP:$API_PORT/preview/stop" > /dev/null
    echo "[*] Stream stopped. Goodbye!"
}

# Trap exit signals to ensure the cleanup function always runs
trap cleanup EXIT INT TERM

echo "[*] Requesting camera preview stream to start on port $PREVIEW_PORT..."
START_RES=$(curl -s -X POST "http://$PI_IP:$API_PORT/preview/start")

if [[ ! "$START_RES" == *"started"* ]]; then
    echo "[!] Stream failed to start natively over HTTP. Response: $START_RES"
    exit 1
fi

echo "[*] Stream enabled successfully."

if command -v ffplay &> /dev/null; then
    echo "[*] Spawning ffplay video viewer..."
    # -x 1280 -y 720 scales the display down so it fits gracefully on Mac screens
    # -fast and -fflags nobuffer reduce streaming latencies
    ffplay -loglevel warning -x 1280 -y 720 -fast -fflags nobuffer "tcp://$PI_IP:$PREVIEW_PORT"
else
    echo "[!] ffplay is not installed."
    echo "    Please open VLC Player -> Open Network -> tcp://$PI_IP:$PREVIEW_PORT"
    echo "    Press [ENTER] in this terminal when you are done to close the stream."
    read -r
fi
