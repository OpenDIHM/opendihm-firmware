"""Tests for the Hardware Controller."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from opendihm_firmware.hardware import HardwareController

@pytest.mark.asyncio
async def test_hardware_controller_real_capture() -> None:
    """Test the HardwareController when not in mock mode."""
    with patch("opendihm_firmware.hardware.LED") as mock_led, \
         patch("opendihm_firmware.hardware.subprocess.run") as mock_run:
        
        # Setup mock subprocess output
        mock_process = MagicMock()
        mock_process.stdout = b"REAL_IMAGE_DATA"
        mock_run.return_value = mock_process
        
        hw = HardwareController(mock_mode=False)
        result = await hw.pulse_laser_and_capture(z_metadata=5.0)
        
        # Assertions
        assert result == b"REAL_IMAGE_DATA"
        mock_led.assert_called_once()
        mock_run.assert_called_once()
        
        # Test subprocess exception handling
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr=b"error")
        result_error = await hw.pulse_laser_and_capture(z_metadata=5.0)
        assert result_error is None

def test_hardware_controller_init_fail() -> None:
    """Test HardwareController initialization failure."""
    with patch("opendihm_firmware.hardware.LED", side_effect=Exception("mock error")):
        hw = HardwareController(mock_mode=False)
        assert hw.laser is None
        
