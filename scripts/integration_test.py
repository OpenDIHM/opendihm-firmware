#!/usr/bin/env python3
"""
Integration test script for OpenDIHM Firmware.

This script validates that the HTTP server, the capture endpoint (DNG data),
and the RTSP/TCP preview stream listeners are working correctly either locally
(via mock mode) or natively on the Raspberry Pi target.
"""

import argparse
import socket
import sys
import time

import httpx


def wait_for_tcp_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Attempts to connect to a TCP port to verify it is listening."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            time.sleep(0.5)
    return False


def test_root(base_url: str) -> None:
    """Validate the root status endpoint."""
    print(f"[*] Testing GET {base_url}/ ...", end=" ")
    try:
        response = httpx.get(f"{base_url}/", timeout=5.0)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "running", "Expected status 'running'"
        print("OK")
    except Exception as e:
        print(f"FAILED\n  Error: {e}")
        sys.exit(1)


def test_capture(base_url: str) -> None:
    """Validate the hologram capture endpoint returning DNG RAW."""
    print(f"[*] Testing POST {base_url}/capture ...", end=" ")
    try:
        response = httpx.post(
            f"{base_url}/capture",
            json={"z_metadata": 10.5},
            timeout=20.0,  # Capturing RAW can take several seconds
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        assert response.headers["content-type"] == "application/octet-stream", (
            f"Expected octet-stream, got {response.headers.get('content-type')}"
        )

        # Validate data
        content_length = len(response.content)
        assert content_length > 0, "Received empty content for capture"

        print(f"OK ({content_length} bytes received)")
    except Exception as e:
        print(f"FAILED\n  Error: {e}")
        sys.exit(1)


def test_preview_lifecycle(base_url: str, host: str, preview_port: int) -> None:
    """Validate starting, connecting to, and stopping the preview stream."""

    # Start Preview
    print(f"[*] Testing POST {base_url}/preview/start ...", end=" ")
    try:
        response = httpx.post(f"{base_url}/preview/start", timeout=5.0)
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data.get("status") == "started", "Expected status 'started'"
        print("OK")
    except Exception as e:
        print(f"FAILED\n  Error: {e}")
        # Not exiting yet, need to stop stream

    # Test TCP Socket for streaming
    print(f"[*] Checking TCP Stream Listen on {host}:{preview_port} ...", end=" ")
    is_listening = wait_for_tcp_port(host, preview_port)
    if is_listening:
        print("OK (Connected)")
    else:
        print("FAILED (Could not establish TCP connection to stream)")

    # Stop Preview
    print(f"[*] Testing POST {base_url}/preview/stop ...", end=" ")
    try:
        response = httpx.post(f"{base_url}/preview/stop", timeout=5.0)
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data.get("status") == "stopped", "Expected status 'stopped'"
        print("OK")
    except Exception as e:
        print(f"FAILED\n  Error: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenDIHM Firmware Integration Test Suite")
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address of the OpenDIHM API or Pi (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP API port (default: 8000)")
    parser.add_argument(
        "--preview-port",
        type=int,
        default=8888,
        help="TCP Stream port used by libcamera-vid (default: 8888)",
    )

    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print("=== OpenDIHM Firmware Integration Tests ===")
    print(f"Targeting HTTP API: {base_url}")
    print(f"Targeting Preview Stream: tcp://{args.host}:{args.preview_port}")
    print("===========================================")

    test_root(base_url)
    test_capture(base_url)
    test_preview_lifecycle(base_url, args.host, args.preview_port)

    print("\nIntegration test suite passed successfully!")


if __name__ == "__main__":
    main()
