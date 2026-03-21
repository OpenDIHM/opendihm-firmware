"""
Hardware interface for OpenDIHM.

Handles interactions with the laser GPIO and the camera module.
"""

import asyncio
import logging
import os
import subprocess
import uuid

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

        self.preview_process: subprocess.Popen[bytes] | None = None
        self.mock_server: asyncio.AbstractServer | None = None

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
                # libcamera cannot encode DNG to stdout natively, it must wrap it in a file.
                # Use /dev/shm/ temporary RAM disk to avoid SD card wear and slow I/O.

                capture_id = str(uuid.uuid4())
                jpg_path = f"/dev/shm/capture_{capture_id}.jpg"
                dng_path = f"/dev/shm/capture_{capture_id}.dng"

                # Options:
                # -e jpg : base encoding (required to generate the DNG sidecar)
                # --raw : generate a sidecar DNG RAW file
                # Dimensions: 3280x2464 (8MP)
                cmd = [
                    "rpicam-still",
                    "--width",
                    "3280",
                    "--height",
                    "2464",
                    "--encoding",
                    "jpg",  # Save JPG to trigger side-car execution
                    "--raw",  # Force side-car RAW DNG output
                    "--shutter",
                    str(exposure_time_us),  # Manual exposure
                    "--awbgains",
                    "1.0,1.0",  # Fixed white balance
                    "--nopreview",
                    "-o",
                    jpg_path,  # Write to RAM disk
                ]

                # Run capture subprocess blocking event loop via run_in_executor
                loop = asyncio.get_running_loop()

                def run_capture() -> None:
                    subprocess.run(cmd, capture_output=True, check=True)
                    # Read the DNG payload into memory
                    nonlocal image_data
                    if os.path.exists(dng_path):
                        with open(dng_path, "rb") as f:
                            image_data = f.read()

                    # Cleanup the RAM disk completely to preserve the Pi's 512MB RAM
                    if os.path.exists(jpg_path):
                        os.unlink(jpg_path)
                    if os.path.exists(dng_path):
                        os.unlink(dng_path)

                await loop.run_in_executor(None, run_capture)

                if image_data is not None:
                    logger.info("Raw DNG Image captured successfully.")
                else:
                    logger.error("DNG output file was not found after capture!")
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

    async def start_preview(self, width: int = 1920, height: int = 1080, fps: int = 30) -> bool:
        """
        Starts the real-time sample alignment preview stream using libcamera-vid.
        The stream listens on TCP port 8888 by default, which can be wrapped
        into RTSP via MediaMTX or read directly.
        """
        if self.preview_process and self.preview_process.poll() is None:
            logger.warning("Preview is already running.")
            return True

        if not self.mock_mode and self.laser:
            self.laser.on()

        logger.info("Starting preview stream...")

        if not self.mock_mode:
            cmd = [
                "rpicam-vid",
                "-t",
                "0",  # Run indefinitely
                "--inline",  # Required for streaming
                "--listen",  # Listen for incoming TCP connection
                "-o",
                "tcp://0.0.0.0:8888",
                "--width",
                str(width),
                "--height",
                str(height),
                "--framerate",
                str(fps),
                "--profile",
                "baseline",
                "--intra",
                "30",
                "--nopreview",
            ]
            try:
                self.preview_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL
                )
                logger.info("libcamera-vid preview process started. Waiting for TCP socket...")
                
                # Wait up to 5 seconds for the port to open without connecting to it
                for _ in range(50):
                    if self.preview_process.poll() is not None:
                        logger.error("Preview process exited prematurely.")
                        return False
                        
                    result = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
                    if ":8888" in result.stdout:
                        logger.info("TCP port 8888 is now listening.")
                        return True
                    await asyncio.sleep(0.1)
                    
                logger.error("Timeout waiting for preview stream port 8888.")
                return False
            except Exception as e:
                logger.error(f"Failed to start preview stream: {e}")
                if self.laser:
                    self.laser.off()
                return False
        else:
            logger.info("Mock hardware: Simulated preview stream started.")
            if self.mock_server is None:

                async def handle_client(
                    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
                ) -> None:
                    pass

                try:
                    self.mock_server = await asyncio.start_server(handle_client, "0.0.0.0", 8888)
                except Exception as e:
                    logger.error(f"Failed to start mock server: {e}")
                    return False
            return True

    async def stop_preview(self) -> bool:
        """Stops the real-time preview stream."""
        logger.info("Stopping preview stream...")

        if not self.mock_mode and self.laser:
            self.laser.off()

        if self.preview_process:
            self.preview_process.terminate()
            try:
                self.preview_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.preview_process.kill()
            self.preview_process = None
            logger.info("Preview process terminated.")

        if self.mock_server:
            self.mock_server.close()
            await self.mock_server.wait_closed()
            self.mock_server = None
            logger.info("Mock preview server stopped.")

        return True
