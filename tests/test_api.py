"""Tests for the NIBE DVC UDP protocol client."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.nibe_dvc.api import (
    NibeDvcNetwork,
    NibeDvcProtocolError,
    parse_network_response,
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
    with pytest.raises(NibeDvcProtocolError):
        parse_response(data)


def test_parse_rejects_undecodable_frame() -> None:
    """A frame whose first parameter is unknown yields nothing and raises."""
    with pytest.raises(NibeDvcProtocolError):
        parse_response(b"master" + bytes([0xFE, 0x00]))


def test_state_missing_values_are_none() -> None:
    """Absent parameters read as None rather than raising or defaulting."""
    state = parse_response(b"master" + bytes([0x04, 0x03]))

    assert state.speed == 3
    assert state.is_on is None
    assert state.airflow is None
    assert state.humidity is None


def test_timers_decode_as_big_endian_seconds() -> None:
    """The 3-byte timer parameters are seconds, not packed h/m/s.

    A real unit reported values that land on exact durations, which is what
    confirms the encoding.
    """
    frame = b"master" + bytes(
        [0x0F, 0x00, 0x70, 0x80]  # night mode timer
        + [0x10, 0x00, 0x38, 0x40]  # party mode timer
        + [0x11, 0x00, 0x02, 0x58]  # deactivation timer
    )
    raw = parse_response(frame).raw

    assert raw["night_mode_timer"] == 28800  # 8 h
    assert raw["party_mode_timer"] == 14400  # 4 h
    assert raw["deactivation_timer"] == 600  # 10 min


async def test_corrupt_frame_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single unparseable datagram is retried rather than failing the poll.

    Parsing used to happen outside the retry loop, so one corrupted packet
    aborted the whole update even though a resend would have succeeded.
    """
    from custom_components.nibe_dvc import api

    good = bytes.fromhex("6d61737465720301040105ff0600")
    replies = [b"master" + bytes([0xFE, 0x00]), good]  # first frame undecodable

    class FakeTransport:
        def sendto(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    async def fake_endpoint(factory, remote_addr=None):
        protocol = factory()
        protocol.future.set_result(replies.pop(0))
        return FakeTransport(), protocol

    # Patch only this one method on the real loop; the protocol object still
    # needs the loop itself to create its future.
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_datagram_endpoint", fake_endpoint)

    state = await api.NibeDvcFan("192.0.2.5", retries=3).async_update()

    assert replies == []  # both frames consumed: it retried
    assert state.is_on is True
    assert state.speed == 1


# A real CMD_NETWORK reply. The password bytes are present on purpose: the
# point of these tests is that they never come back out.
PASSWORD_IN_FRAME = "supersecr1"


def _network_frame(ssid: str, password: str, ip: tuple[int, ...]) -> bytes:
    """Build a CMD_NETWORK reply the way the unit does."""
    return (
        b"master"
        + bytes([0x23, *ip])
        + bytes([0x20, len(ssid)])
        + ssid.encode()
        + bytes([0x21, len(password)])
        + password.encode()
        + bytes([0x22])
        + b"\r\n"
    )


NETWORK_FRAME = _network_frame("my-home-wifi", PASSWORD_IN_FRAME, (192, 0, 2, 5))


def test_parse_network_frame() -> None:
    """SSID and IP are decoded from the network frame."""
    network = parse_network_response(NETWORK_FRAME)

    assert network.ssid == "my-home-wifi"
    assert network.ip_address == "192.0.2.5"


def test_network_frame_password_is_discarded() -> None:
    """The Wi-Fi password must never survive parsing.

    The unit hands it out in plaintext to anyone on the network. Keeping it
    would put it one bug report away from being published.
    """
    network = parse_network_response(NETWORK_FRAME)

    assert PASSWORD_IN_FRAME in NETWORK_FRAME.decode("latin1")  # it *is* on the wire
    assert PASSWORD_IN_FRAME not in repr(network)
    assert PASSWORD_IN_FRAME not in str(vars(NibeDvcNetwork).get("__doc__") or "")
    for value in (network.ssid, network.ip_address):
        assert value is None or PASSWORD_IN_FRAME not in value


@pytest.mark.parametrize("data", [b"", b"master"])
def test_parse_network_rejects_short_frames(data: bytes) -> None:
    """A frame with no body is rejected rather than returning empty settings."""
    with pytest.raises(NibeDvcProtocolError):
        parse_network_response(data)


def test_parse_network_rejects_undecodable_frame() -> None:
    """A frame with no recognisable network parameter raises."""
    with pytest.raises(NibeDvcProtocolError):
        parse_network_response(b"master" + bytes([0xFE, 0x00]))
