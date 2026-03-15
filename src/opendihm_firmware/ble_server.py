"""
Bluetooth Low Energy (GATT) Server for OpenDIHM.

Allows an iOS device to connect offline, transmit Wi-Fi credentials securely,
and provision the headless Raspberry Pi to join the local network.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any

from bless import (  # type: ignore
    BlessGATTCharacteristic,
    BlessServer,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)

logger = logging.getLogger(__name__)

# Custom OpenDIHM UUIDs
SERVICE_UUID = "cd1dd15c-3cda-48eb-bbd9-93ef640fe50b"
WIFI_CHAR_UUID = "cd1dd15d-3cda-48eb-bbd9-93ef640fe50b"
STATUS_CHAR_UUID = "cd1dd15e-3cda-48eb-bbd9-93ef640fe50b"

DEVICE_NAME = "OpenDIHM"


class BLEConfigServer:
    """Manages the BLE GATT Server for Wi-Fi Provisioning."""

    def __init__(self, mock_mode: bool = False) -> None:
        """Initialize the BLE config server.

        Args:
            mock_mode: If True, skip real Bluetooth hardware; useful for local testing.
        """
        self.mock_mode = mock_mode

        # BlessServer is instantiated lazily inside start() so that it is always
        # created within a running asyncio event loop (required by bless/CoreBluetooth).
        self.server: BlessServer | None = None

        # Flag to indicate if we've successfully connected so we can stop the server
        self.connected_to_wifi = False

    def setup(self) -> None:
        """Configures the BLE services and characteristics."""
        assert self.server is not None
        logger.info(f"Setting up BLE Server with UUID {SERVICE_UUID}")

        # Add the primary configuration service
        self.server.add_new_service(SERVICE_UUID)

        # Wi-Fi Credentials Characteristic (Write Only)
        # Expected JSON: {"ssid": "Your Network", "pwd": "Your Password"}
        char_flags = GATTCharacteristicProperties.write
        permissions = GATTAttributePermissions.writeable

        self.server.add_new_characteristic(
            SERVICE_UUID,
            WIFI_CHAR_UUID,
            char_flags,
            bytearray(b""),
            permissions,
        )

        # Status Characteristic (Read/Notify)
        status_flags = GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
        status_permissions = GATTAttributePermissions.readable

        self.server.add_new_characteristic(
            SERVICE_UUID,
            STATUS_CHAR_UUID,
            status_flags,
            bytearray(b"Ready"),
            status_permissions,
        )

        # Define callbacks
        self.server.read_request_func = self.on_read
        self.server.write_request_func = self.on_write

    def on_read(self, characteristic: BlessGATTCharacteristic, **kwargs: Any) -> bytearray:
        """Handle incoming read requests."""
        logger.debug(f"Reading characteristic: {characteristic.uuid}")
        return bytearray(characteristic.value)

    def on_write(self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs: Any) -> None:
        """Handle incoming write requests (Wi-Fi credentials)."""
        characteristic.value = value
        logger.info(f"Write request on {characteristic.uuid}")

        if characteristic.uuid.lower() == WIFI_CHAR_UUID.lower():
            try:
                charset = value.decode("utf-8")
                creds = json.loads(charset)
                ssid = creds.get("ssid")
                pwd = creds.get("pwd")

                if ssid and pwd:
                    self.update_status(f"Connecting to {ssid}...")
                    # We run the command asynchronously to not block the GATT thread
                    asyncio.create_task(self.connect_to_wifi(ssid, pwd))
                else:
                    self.update_status("Error: Missing SSID or Password")

            except json.JSONDecodeError:
                logger.error("Failed to decode Wi-Fi credentials payload.")
                self.update_status("Error: Invalid JSON format")
            except Exception as e:
                logger.error(f"Error handling Wi-Fi payload: {e}")
                self.update_status("Error: Processing failed")

    def update_status(self, message: str) -> None:
        """Update the status characteristic and notify any subscribers."""
        assert self.server is not None
        logger.info(f"BLE Status: {message}")
        self.server.get_characteristic(STATUS_CHAR_UUID).value = bytearray(message.encode("utf-8"))
        self.server.update_value(SERVICE_UUID, STATUS_CHAR_UUID)

    async def connect_to_wifi(self, ssid: str, pwd: str) -> None:
        """Connects the Raspberry Pi to the target Wi-Fi network using NetworkManager."""
        logger.info(f"Attempting to connect to Wi-Fi SSID: {ssid}")

        try:
            # Modern Raspberry Pi OS (Bookworm) uses NetworkManager via nmcli
            # For this MVP, we execute the shell command to add and connect
            cmd = [
                "nmcli",
                "device",
                "wifi",
                "connect",
                ssid,
                "password",
                pwd,
            ]

            # Use run_in_executor to not block the asyncio loop
            loop = asyncio.get_running_loop()

            def run_nmcli() -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(cmd, capture_output=True, check=False)

            result = await loop.run_in_executor(None, run_nmcli)

            if result.returncode == 0:
                logger.info("Successfully connected to Wi-Fi!")
                self.update_status("Connected")
                self.connected_to_wifi = True
            else:
                error_msg = result.stderr.decode().strip()
                logger.error(f"Failed to connect: {error_msg}")
                self.update_status("Failed to connect")

        except Exception as e:
            logger.error(f"nmcli exception: {e}")
            self.update_status("Error: nmcli failed")

    async def start(self) -> None:
        """Start advertising the BLE server."""
        if self.mock_mode:
            logger.info("Mock mode: BLE Server is disabled. Skipping Bluetooth advertisement.")
            return

        # Lazily create BlessServer here, inside the running asyncio event loop.
        # bless/CoreBluetooth requires an active loop at construction time.
        self.server = BlessServer(name=DEVICE_NAME)
        self.setup()
        await self.server.start()
        logger.info(f"Advertising {DEVICE_NAME} BLE Server...")

        # Keep alive indefinitely until Wi-Fi is configured
        while not self.connected_to_wifi:
            await asyncio.sleep(2)

        logger.info("Wi-Fi connected. Shutting down BLE advertisement.")
        await self.server.stop()
