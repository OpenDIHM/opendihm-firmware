"""
Hardware interface for OpenDIHM.

Handles interactions with the laser GPIO and the camera module.
"""

import asyncio
import logging
import subprocess

from gpiozero import LED  # type: ignore

logger = logging.getLogger(__name__)

# Pin 17 defined in design document for NPN Transistor laser pulse
LASER_GPIO_PIN = 17


class HardwareController:
    """Controller for physical hardware components of OpenDIHM."""

    def __init__(self, mock_mode: bool = False) -> None:
        """Initialize the hardware controller.

        Args:
            mock_mode: If True, do not try to access real GPIO/Camera hardware, useful for testing.
        """
        self.mock_mode = mock_mode
        if not self.mock_mode:
            try:
                self.laser = LED(LASER_GPIO_PIN)
            except Exception as e:
                logger.error(f"Failed to initialize GPIO {LASER_GPIO_PIN}: {e}")
                self.laser = None  # Fallback gracefully
        else:
            self.laser = None

    async def pulse_laser_and_capture(
        self, z_metadata: float, exposure_time_us: int = 10000
    ) -> bytes | None:
        """
        Pulsing logic for holography capture.

        Steps:
        1. Pulse GPIO 17 HIGH (+50ms lead time)
        2. Camera captures a full 8MP frame (3280x2464).
        3. Returns the bytes of the captured file.
        """
        if not self.mock_mode and self.laser:
            self.laser.on()
        logger.info(f"Laser ON. Preparing capture for z={z_metadata}")

        # 50ms lead time as requested in design document
        await asyncio.sleep(0.05)

        image_data: bytes | None = None

        try:
            if not self.mock_mode:
                # Use libcamera-still to capture image
                # Options:
                # -e dng : encode as RAW DNG
                # Let's save to stdout (-) and return byte content.
                # Dimensions: 3280x2464 (8MP)
                cmd = [
                    "libcamera-still",
                    "--width",
                    "3280",
                    "--height",
                    "2464",
                    "--encoding",
                    "dng",
                    "--raw",  # Force RAW DNG output
                    "--shutter",
                    str(exposure_time_us),  # Manual exposure
                    "--awbgains",
                    "1.0,1.0",  # Fixed white balance
                    "--nopreview",
                    "-o",
                    "-",  # output to stdout
                ]

                # Run capture subprocess blocks event loop without asyncio, using run_in_executor
                loop = asyncio.get_running_loop()

                def run_capture() -> subprocess.CompletedProcess[bytes]:
                    return subprocess.run(cmd, capture_output=True, check=True)

                result = await loop.run_in_executor(None, run_capture)
                image_data = result.stdout
                logger.info("Image captured successfully.")
            else:
                logger.info("Mock hardware: Simulating 800ms camera capture delay...")
                await asyncio.sleep(0.8)
                image_data = b"MOCK_JPEG_IMAGE_DATA_WITH_Z=" + str(z_metadata).encode()

        except subprocess.CalledProcessError as e:
            logger.error(f"Camera capture failed: {e.stderr.decode()}")
        finally:
            if not self.mock_mode and self.laser:
                self.laser.off()
            logger.info("Laser OFF.")

        return image_data
