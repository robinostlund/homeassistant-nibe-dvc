"""Tests for the EcoVent UDP protocol client."""

from __future__ import annotations

import pytest

from custom_components.ecovent.api import (
    EcoventProtocolError,
    parse_response,
)

from .conftest import REAL_FRAME


def test_parse_real_frame() -> None:
    """A frame captured from real hardware decodes to the expected values."""
    state = parse_response(REAL_FRAME)

    assert state.is_on is True
    assert state.speed == 1
    assert state.manual_speed == 255
    assert state.airflow == 0
    assert state.humidity == 55
    # Multi byte timer parameters are kept for diagnostics.
    assert state.raw["party_or_night_mode_countdown"] == 0
    assert state.raw["filter_eol_timer"] == 1


def test_parse_stops_at_unknown_parameter() -> None:
    """An unknown parameter id keeps what was decoded instead of raising.

    Parameter lengths are what let us walk the frame, so an unknown id means we
    can no longer find the next boundary -- but the values already decoded are
    still good.
    """
    frame = b"master" + bytes([0x03, 0x01, 0x04, 0x02, 0xFE, 0x99])
    state = parse_response(frame)

    assert state.is_on is True
    assert state.speed == 2
    assert "airflow" not in state.raw


def test_parse_truncated_payload() -> None:
    """A payload cut short mid parameter does not raise."""
    frame = b"master" + bytes([0x03, 0x01, 0x0E, 0x00])  # 0x0E needs 3 bytes
    state = parse_response(frame)

    assert state.is_on is True
    assert "party_or_night_mode_countdown" not in state.raw


@pytest.mark.parametrize("data", [b"", b"mast", b"master"])
def test_parse_rejects_short_frames(data: bytes) -> None:
    """Frames with no body are rejected."""
    with pytest.raises(EcoventProtocolError):
        parse_response(data)


def test_parse_rejects_undecodable_frame() -> None:
    """A frame whose first parameter is unknown yields nothing and raises."""
    with pytest.raises(EcoventProtocolError):
        parse_response(b"master" + bytes([0xFE, 0x00]))


def test_state_missing_values_are_none() -> None:
    """Absent parameters read as None rather than raising or defaulting."""
    state = parse_response(b"master" + bytes([0x04, 0x03]))

    assert state.speed == 3
    assert state.is_on is None
    assert state.airflow is None
    assert state.humidity is None
