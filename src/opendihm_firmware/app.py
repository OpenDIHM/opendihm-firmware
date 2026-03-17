"""
FastAPI application for OpenDIHM.

Provides HTTP/REST endpoints for controlling the microscope.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from opendihm_firmware.ble_server import BLEConfigServer
from opendihm_firmware.hardware import HardwareController

# Initialize hardware controller depending on debug env flag
mock_mode = os.environ.get("OPENDIHM_DEBUG", "false").lower() == "true"
hardware = HardwareController(mock_mode=mock_mode)
ble_server = BLEConfigServer(mock_mode=mock_mode)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the application lifespan, including BLE server lifecycle."""
    # Start BLE server as a background task alongside the HTTP API
    ble_task = asyncio.create_task(ble_server.start())
    yield
    # Shutdown: Cancel the background BLE task gracefully when uvicorn stops
    ble_task.cancel()
    try:
        await ble_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="OpenDIHM Firmware API", lifespan=lifespan)


class CaptureRequest(BaseModel):
    """Payload for the /capture endpoint."""

    z_metadata: float


@app.get("/")
def read_root() -> dict[str, str]:
    """Root endpoint to check service status."""
    return {"status": "running", "microscope": "OpenDIHM"}


@app.post("/capture")
async def capture_hologram(payload: CaptureRequest) -> Response:
    """
    Triggers a capture operation.

    Expects z_metadata representing the Z-distance for metadata tracking.
    """
    img_data = await hardware.pulse_laser_and_capture(z_metadata=payload.z_metadata)

    if img_data is None:
        raise HTTPException(status_code=500, detail="Failed to capture image via hardware.")

    # Return as RAW DNG byte stream
    return Response(content=img_data, media_type="application/octet-stream")


@app.post("/preview/start")
async def start_preview() -> dict[str, str]:
    """Starts the real-time sample alignment RTSP-capable preview stream."""
    success = await hardware.start_preview()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start preview stream.")
    return {"status": "started", "port": "8888"}


@app.post("/preview/stop")
async def stop_preview() -> dict[str, str]:
    """Stops the real-time preview stream."""
    await hardware.stop_preview()
    return {"status": "stopped"}


def start_server() -> None:
    """Helper method to start the uvicorn server directly."""
    import uvicorn

    host = os.environ.get("OPENDIHM_HOST", "::")
    port = int(os.environ.get("OPENDIHM_PORT", "8000"))
    uvicorn.run("opendihm_firmware.app:app", host=host, port=port, reload=mock_mode)


if __name__ == "__main__":
    start_server()
