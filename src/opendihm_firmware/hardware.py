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
        self.preview_params: dict[str, int] = {"width": 1920, "height": 1080, "fps": 30}
        self.exposure_time_us: int = 10000

    async def pulse_laser_and_capture(
        self, z_metadata: float, exposure_time_us: int | None = None
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

        # Stop preview if running — libcamera pipeline is exclusive
        preview_was_running = self._preview_is_running()
        if preview_was_running:
            logger.info("Preview in progress; stopping it temporarily for capture.")
            await self.stop_preview()

        try:
            if not self.mock_mode:
                # Use libcamera-still to capture image
                # libcamera cannot encode DNG to stdout natively, it must wrap it in a file.
                # Use /dev/shm/ temporary RAM disk to avoid SD card wear and slow I/O.

                capture_id = str(uuid.uuid4())
                primary_path = f"/dev/shm/capture_{capture_id}.jpg"
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
                    str(exposure_time_us or self.exposure_time_us),  # Manual exposure
                    "--awbgains",
                    "1.0,1.0",  # Fixed white balance
                    "--nopreview",
                    "-o",
                    primary_path,  # Write to RAM disk
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
                    if os.path.exists(primary_path):
                        os.unlink(primary_path)
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
            # Restart preview if it was running before capture
            if preview_was_running:
                logger.info("Restarting preview stream after capture.")
                await self.start_preview(**self.preview_params)

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

        self.preview_params.update(width=width, height=height, fps=fps)
        logger.info("Starting preview stream...")

        if self.mock_mode:
            return await self._start_mock_preview()

        return await self._start_real_preview(width, height, fps)

    async def _start_mock_preview(self) -> bool:
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

    async def _start_real_preview(self, width: int, height: int, fps: int) -> bool:
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
            self.preview_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL)
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

    def _preview_is_running(self) -> bool:
        """Check whether the real or mock preview stream is currently active."""
        if self.mock_server is not None:
            return True
        return self.preview_process is not None and self.preview_process.poll() is None

    def get_system_status(self) -> dict[str, float | int | bool]:
        """Returns hardware system status metrics."""
        status: dict[str, float | int | bool] = {
            "temperature_c": 0.0,
            "wifi_signal_dbm": 0,
            "laser_on": False,
            "exposure_time_us": self.exposure_time_us,
            "storage_left_bytes": 0,
            "memory_left_bytes": 0,
        }

        if self.mock_mode:
            status.update(
                {
                    "temperature_c": 45.0,
                    "wifi_signal_dbm": -50,
                    "storage_left_bytes": 10 * 1024 * 1024 * 1024,
                    "memory_left_bytes": 256 * 1024 * 1024,
                }
            )
            return status

        status["temperature_c"] = self._get_temperature()
        status["wifi_signal_dbm"] = self._get_wifi_signal()
        status["storage_left_bytes"] = self._get_storage_left()
        status["memory_left_bytes"] = self._get_memory_left()

        if self.laser:
            status["laser_on"] = self.laser.is_active

        return status

    def _get_temperature(self) -> float:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            return 0.0

    def _get_wifi_signal(self) -> float:
        try:
            with open("/proc/net/wireless") as f:
                lines = f.readlines()
                if len(lines) > 2:
                    for line in lines[2:]:
                        parts = line.split()
                        if "wlan" in parts[0]:
                            return float(parts[3].replace(".", ""))
        except Exception:
            pass
        return 0.0

    def _get_storage_left(self) -> int:
        try:
            import shutil

            return shutil.disk_usage("/").free
        except Exception:
            return 0

    def _get_memory_left(self) -> int:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) * 1024
        except Exception:
            pass
        return 0
