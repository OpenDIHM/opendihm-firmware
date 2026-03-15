"""
Tests for opendihm_firmware package.
"""

from opendihm_firmware import get_status


def test_get_status() -> None:
    """Test the basic get_status method."""
    status = get_status()
    assert status == {"status": "initialized"}
