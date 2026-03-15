"""
FastAPI application for OpenDIHM.

Provides HTTP/REST endpoints for controlling the microscope.
"""

import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from opendihm_firmware.hardware import HardwareController

app = FastAPI(title="OpenDIHM Firmware API")

# Initialize hardware controller depending on debug env flag
mock_mode = os.environ.get("OPENDIHM_DEBUG", "false").lower() == "true"
hardware = HardwareController(mock_mode=mock_mode)


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

    # Return as JPEG bytes stream
    return Response(content=img_data, media_type="image/jpeg")


def start_server() -> None:
    """Helper method to start the uvicorn server directly."""
    import uvicorn

    host = os.environ.get("OPENDIHM_HOST", "0.0.0.0")
    port = int(os.environ.get("OPENDIHM_PORT", "8000"))
    uvicorn.run("opendihm_firmware.app:app", host=host, port=port, reload=mock_mode)


if __name__ == "__main__":
    start_server()
