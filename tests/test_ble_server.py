"""Tests for the BLE GATT Configuration Server."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opendihm_firmware.ble_server import (
    SERVICE_UUID,
    STATUS_CHAR_UUID,
    WIFI_CHAR_UUID,
    BLEConfigServer,
)


@pytest.mark.asyncio
async def test_ble_server_mock_mode_skips_bluetooth() -> None:
    """Verify that in mock mode, the BLE server simply returns without touching hardware."""
    server = BLEConfigServer(mock_mode=True)
    # Should return immediately without any Bluetooth calls
    await server.start()
    assert server.connected_to_wifi is False


@pytest.mark.asyncio
async def test_ble_server_real_mode_advertises() -> None:
    """Verify the BLE server calls start and stop on BlessServer in real mode."""
    with patch("opendihm_firmware.ble_server.BlessServer") as mock_bless_cls:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_bless_cls.return_value = mock_instance

        server = BLEConfigServer(mock_mode=False)
        # Mark as connected immediately so the loop exits
        server.connected_to_wifi = True

        await server.start()

        mock_instance.start.assert_called_once()
        mock_instance.stop.assert_called_once()


def test_update_status_updates_characteristic() -> None:
    """Verify update_status sets the correct value on the status characteristic."""
    mock_char = MagicMock()
    mock_char.value = bytearray(b"Ready")

    mock_instance = MagicMock()
    mock_instance.get_characteristic.return_value = mock_char

    server = BLEConfigServer(mock_mode=False)
    # Inject the mock server instance directly (server is normally lazy-created in start())
    server.server = mock_instance

    server.update_status("Testing")

    assert mock_char.value == bytearray(b"Testing")
    mock_instance.update_value.assert_called_once_with(SERVICE_UUID, STATUS_CHAR_UUID)


@pytest.mark.asyncio
async def test_on_write_valid_wifi_credentials() -> None:
    """Verify that valid JSON credentials trigger an asyncio task for nmcli."""
    with patch("opendihm_firmware.ble_server.BlessServer"):
        server = BLEConfigServer(mock_mode=False)

        mock_char = MagicMock()
        mock_char.uuid = WIFI_CHAR_UUID

        creds = json.dumps({"ssid": "TestNetwork", "pwd": "TestPass"}).encode()

        with patch.object(server, "update_status") as mock_status:
            with patch("asyncio.create_task") as mock_task:
                server.on_write(mock_char, bytearray(creds))
                mock_status.assert_called_with("Connecting to TestNetwork...")
                mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_on_write_invalid_json() -> None:
    """Verify that malformed JSON triggers an error status update."""
    with patch("opendihm_firmware.ble_server.BlessServer"):
        server = BLEConfigServer(mock_mode=False)

        mock_char = MagicMock()
        mock_char.uuid = WIFI_CHAR_UUID

        with patch.object(server, "update_status") as mock_status:
            server.on_write(mock_char, bytearray(b"not-valid-json"))
            mock_status.assert_called_with("Error: Invalid JSON format")


@pytest.mark.asyncio
async def test_connect_wifi_success() -> None:
    """Verify successful nmcli connection sets connected_to_wifi to True."""
    with patch("opendihm_firmware.ble_server.BlessServer"):
        server = BLEConfigServer(mock_mode=False)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("opendihm_firmware.ble_server.subprocess.run", return_value=mock_result),
            patch.object(server, "update_status") as mock_status,
        ):
            await server.connect_to_wifi("TestNetwork", "TestPass")
            assert server.connected_to_wifi is True
            mock_status.assert_called_with("Connected")


@pytest.mark.asyncio
async def test_connect_wifi_failure() -> None:
    """Verify that an nmcli failure sets an error status and does not set connected_to_wifi."""
    with patch("opendihm_firmware.ble_server.BlessServer"):
        server = BLEConfigServer(mock_mode=False)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"Error: No such SSID"

        with (
            patch("opendihm_firmware.ble_server.subprocess.run", return_value=mock_result),
            patch.object(server, "update_status") as mock_status,
        ):
            await server.connect_to_wifi("BadNetwork", "WrongPass")
            assert server.connected_to_wifi is False
            mock_status.assert_called_with("Failed to connect")
