"""Tests for the Hardware Controller."""

import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from opendihm_firmware.hardware import HardwareController


@pytest.mark.asyncio
async def test_hardware_controller_real_capture() -> None:
    """Test the HardwareController when not in mock mode."""
    with (
        patch("opendihm_firmware.hardware.LED") as mock_led,
        patch("opendihm_firmware.hardware.subprocess.run") as mock_run,
        patch("opendihm_firmware.hardware.os.path.exists", return_value=True),
        patch("opendihm_firmware.hardware.os.unlink") as mock_unlink,
        patch("builtins.open", mock_open(read_data=b"REAL_IMAGE_DATA")),
    ):
        mock_run.return_value = MagicMock()

        hw = HardwareController(mock_mode=False)
        result = await hw.pulse_laser_and_capture(z_metadata=5.0)

        # Assertions
        assert result == b"REAL_IMAGE_DATA"
        mock_led.assert_called_once()
        mock_run.assert_called_once()
        assert mock_unlink.call_count == 2  # Unlinks both jpg and dng

        # Test subprocess exception handling
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr=b"error")
        result_error = await hw.pulse_laser_and_capture(z_metadata=5.0)
        assert result_error is None


def test_hardware_controller_init_fail() -> None:
    """Test HardwareController initialization failure."""
    with patch("opendihm_firmware.hardware.LED", side_effect=Exception("mock error")):
        hw = HardwareController(mock_mode=False)
        assert hw.laser is None


@pytest.mark.asyncio
async def test_preview_start_stop_real() -> None:
    """Test starting and stopping real preview stream."""
    with (
        patch("opendihm_firmware.hardware.LED") as mock_led,
        patch("opendihm_firmware.hardware.subprocess.Popen") as mock_popen,
        patch("opendihm_firmware.hardware.subprocess.run") as mock_run,
    ):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        mock_run_result = MagicMock()
        mock_run_result.stdout = ":8888\n"
        mock_run.return_value = mock_run_result

        hw = HardwareController(mock_mode=False)

        # Test start
        success = await hw.start_preview()
        assert success is True
        mock_led.assert_called_once()
        mock_popen.assert_called_once()
        assert hw.preview_process is not None

        # Test start again (should do nothing)
        success_again = await hw.start_preview()
        assert success_again is True
        assert mock_popen.call_count == 1

        # Test stop
        stop_success = await hw.stop_preview()
        assert stop_success is True
        mock_process.terminate.assert_called_once()
        assert hw.preview_process is None


@pytest.mark.asyncio
async def test_preview_start_fail_real() -> None:
    """Test start preview failing."""
    with (
        patch("opendihm_firmware.hardware.LED"),
        patch("opendihm_firmware.hardware.subprocess.Popen", side_effect=Exception("error")),
    ):
        hw = HardwareController(mock_mode=False)
        success = await hw.start_preview()
        assert success is False
        assert hw.preview_process is None
