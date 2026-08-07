"""Tests for the NIBE DVC UDP protocol client."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.nibe_dvc import api
from custom_components.nibe_dvc.api import (
    NibeDvcNetwork,
    NibeDvcProtocolError,
    parse_config_response,
    parse_network_response,
    parse_response,
)

from .conftest import (
    REAL_CONFIG_FRAME,
    REAL_FRAME,
    TEST_HOST,
    FakeUnit,
    config_frame,
    status_frame,
)


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


def test_status_frame_is_not_accepted_as_config() -> None:
    """A status frame must never decode as a config frame.

    Both frames share the parameter table, so without a guard a stray status
    frame -- which PROTOCOL.md records the unit really does send -- would decode
    into a config whose every setting reads None. That is silent and permanent:
    the number entities and the trigger binary sensors are built from the config
    frame at setup, so they would simply never be created.
    """
    with pytest.raises(NibeDvcProtocolError):
        parse_config_response(REAL_FRAME)


def test_real_config_frame_still_parses() -> None:
    """The guard must not reject an actual config frame."""
    config = parse_config_response(REAL_CONFIG_FRAME)

    assert config.humidity_threshold == 75
    assert config.deactivation_delay == 600
    assert config.humidity_sensor_enabled is True
    assert config.sensor_10v_enabled is False
    assert config.raw["night_mode_timer"] == 28800


async def test_wrong_frame_type_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """The config read survives the unit answering with the wrong frame."""
    replies = [REAL_FRAME, REAL_CONFIG_FRAME]  # first one is a status frame

    unit = FakeUnit(monkeypatch, lambda request: replies.pop(0))
    config = await api.NibeDvcFan(TEST_HOST).async_get_config()

    assert replies == []  # both consumed: it asked again
    assert config.humidity_threshold == 75
    assert unit.commands == [api.CMD_CONFIG, api.CMD_CONFIG]


async def test_power_toggle_only_when_state_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit only exposes a toggle, so turning "on" while on must be a no-op."""
    unit = FakeUnit(monkeypatch, lambda request: status_frame(state=1))
    fan = api.NibeDvcFan(TEST_HOST)

    state = await fan.async_set_power(True)

    assert state.is_on is True
    assert unit.commands == [api.CMD_STATUS]  # read only, no toggle sent


async def test_power_toggle_sent_when_state_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turning on a stopped unit sends the toggle."""
    running = {"on": False}

    def handler(request: bytes) -> bytes:
        if request[len(api.REQUEST_HEADER)] == api.CMD_TOGGLE_POWER:
            running["on"] = not running["on"]
        return status_frame(state=int(running["on"]))

    unit = FakeUnit(monkeypatch, handler)
    state = await api.NibeDvcFan(TEST_HOST).async_set_power(True)

    assert unit.commands == [api.CMD_STATUS, api.CMD_TOGGLE_POWER]
    assert state.is_on is True


async def test_config_write_is_resent_until_it_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent config write that gets lost must be retransmitted.

    The unit answers these writes with nothing at all, so the request/response
    retry has no reply to trigger on. Without reading the value back and
    resending, a single dropped datagram would leave the setting untouched and
    report success.
    """
    stored = {"threshold": 75}
    dropped = {"count": 0}

    def handler(request: bytes) -> bytes | None:
        command = request[len(api.REQUEST_HEADER)]
        if command == api.CMD_HUMIDITY_THRESHOLD:
            if dropped["count"] < 1:
                dropped["count"] += 1  # first write never reaches the unit
                return None
            stored["threshold"] = request[len(api.REQUEST_HEADER) + 1]
            return None  # applied silently, as the real unit does
        return config_frame(humidity_sensor_threshold=stored["threshold"])

    unit = FakeUnit(monkeypatch, handler)
    config = await api.NibeDvcFan(TEST_HOST).async_set_humidity_threshold(60)

    assert config.humidity_threshold == 60
    assert unit.commands.count(api.CMD_HUMIDITY_THRESHOLD) == 2


async def test_config_write_reports_what_the_unit_actually_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write that never takes reports the real value rather than the wish."""
    unit = FakeUnit(
        monkeypatch,
        lambda request: (
            None
            if request[len(api.REQUEST_HEADER)] == api.CMD_HUMIDITY_THRESHOLD
            else config_frame(humidity_sensor_threshold=75)
        ),
    )

    config = await api.NibeDvcFan(TEST_HOST, retries=2).async_set_humidity_threshold(60)

    assert config.humidity_threshold == 75  # honest, not optimistic
    assert unit.commands.count(api.CMD_HUMIDITY_THRESHOLD) == 2  # gave up after retries


async def test_deactivation_delay_is_written_as_three_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run-on delay goes out as a big-endian 3 byte second count."""
    unit = FakeUnit(
        monkeypatch,
        lambda request: (
            None
            if request[len(api.REQUEST_HEADER)] == api.CMD_DEACTIVATION_DELAY
            else config_frame(deactivation_timer=900)
        ),
    )

    await api.NibeDvcFan(TEST_HOST).async_set_deactivation_delay(900)

    write = next(
        r
        for r in unit.requests
        if r[len(api.REQUEST_HEADER)] == api.CMD_DEACTIVATION_DELAY
    )
    payload = write[len(api.REQUEST_HEADER) + 1 : -len(api.REQUEST_FOOTER)]
    assert payload == bytes([0x00, 0x03, 0x84])  # 900 seconds


async def test_silent_write_leaves_no_unretrieved_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ICMP error on a fire-and-forget write must not be left dangling.

    Nothing ever awaits the future behind a silent write, so an exception set on
    it would only ever be seen by the garbage collector -- which asyncio reports
    as "Future exception was never retrieved" at ERROR level, in the user's log,
    for a write that was fine.
    """
    unit = FakeUnit(monkeypatch, lambda request: None)
    fan = api.NibeDvcFan(TEST_HOST)

    async with fan._lock:
        await fan._send_locked(api.CMD_HUMIDITY_THRESHOLD, bytes([60]))

    protocol = unit.protocols[0]

    # The write is finished, so the future must already be settled rather than
    # left pending for a late error to land on. This is the assertion that
    # catches the bug: an abandoned pending future is exactly what lets an
    # incoming ICMP error become an exception nobody reads.
    assert protocol.future.done()
    assert protocol.future.cancelled()

    # A late error now finds a settled future and has nowhere to store itself.
    protocol.error_received(OSError(61, "Connection refused"))
    assert protocol.future.cancelled()


@pytest.mark.parametrize("speed", [0, 4, 255])
async def test_invalid_speed_is_rejected_before_sending(
    monkeypatch: pytest.MonkeyPatch, speed: int
) -> None:
    """Out of range speeds never reach the wire."""
    unit = FakeUnit(monkeypatch, lambda request: status_frame())

    with pytest.raises(ValueError, match="Speed must be"):
        await api.NibeDvcFan(TEST_HOST).async_set_speed(speed)

    assert unit.requests == []


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("async_set_airflow", 3),
        ("async_set_humidity_threshold", 39),
        ("async_set_humidity_threshold", 81),
        ("async_set_deactivation_delay", -1),
        ("async_set_deactivation_delay", 24 * 60 * 60 + 1),
    ],
)
async def test_out_of_range_writes_are_rejected(
    monkeypatch: pytest.MonkeyPatch, method: str, value: int
) -> None:
    """Every setter validates against the range the protocol documents."""
    unit = FakeUnit(monkeypatch, lambda request: status_frame())

    with pytest.raises(ValueError):
        await getattr(api.NibeDvcFan(TEST_HOST), method)(value)

    assert unit.requests == []
