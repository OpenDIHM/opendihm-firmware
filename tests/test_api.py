"""Tests for the FastAPI application."""

from fastapi.testclient import TestClient

from opendihm_firmware.app import app, hardware

client = TestClient(app)


def test_read_root() -> None:
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "running", "microscope": "OpenDIHM"}


def test_capture_endpoint_mock() -> None:
    """Test the /capture endpoint in mock mode."""
    # Ensure hardware is in mock mode for test
    original_mode = hardware.mock_mode
    hardware.mock_mode = True

    # We use TestClient which is synchronous, so it will wait for the async endpoint
    response = client.post("/capture", json={"z_metadata": 12.5})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert b"MOCK_JPEG_IMAGE_DATA_WITH_Z=12.5" in response.content

    hardware.mock_mode = original_mode


def test_capture_endpoint_fail() -> None:
    """Test the /capture endpoint when hardware fails."""
    from unittest.mock import patch

    with patch.object(hardware, "pulse_laser_and_capture", return_value=None):
        response = client.post("/capture", json={"z_metadata": 10.0})
        assert response.status_code == 500
        assert response.json() == {"detail": "Failed to capture image via hardware."}


def test_capture_endpoint_invalid() -> None:
    """Test the /capture endpoint with invalid payload."""
    response = client.post("/capture", json={"wrong": "payload"})
    assert response.status_code == 422  # Unprocessable Entity (ValidationError)


def test_preview_start_mock() -> None:
    """Test starting the preview stream."""
    original_mode = hardware.mock_mode
    hardware.mock_mode = True

    response = client.post("/preview/start")
    assert response.status_code == 200
    assert response.json() == {"status": "started", "port": "8888"}

    hardware.mock_mode = original_mode


def test_preview_start_fail() -> None:
    """Test preview stream start failure."""
    from unittest.mock import patch

    with patch.object(hardware, "start_preview", return_value=False):
        response = client.post("/preview/start")
        assert response.status_code == 500
        assert response.json() == {"detail": "Failed to start preview stream."}


def test_preview_stop_mock() -> None:
    """Test stopping the preview stream."""
    original_mode = hardware.mock_mode
    hardware.mock_mode = True

    response = client.post("/preview/stop")
    assert response.status_code == 200
    assert response.json() == {"status": "stopped"}

    hardware.mock_mode = original_mode
