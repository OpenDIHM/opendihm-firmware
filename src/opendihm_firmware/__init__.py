"""
OpenDIHM Firmware Component.

This module provides the core functionality to interact with the camera and
hardware for the digital inline holographic microscope.
"""

__version__ = "0.1.0"


def get_status() -> dict[str, str]:
    """
    Returns the current status of the firmware.

    Returns:
        A dictionary containing status information.
    """
    return {"status": "initialized"}
