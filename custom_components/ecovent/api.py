"""Asyncio UDP client for Vents/Blauberg TwinFresh style ventilation units.

The protocol is a very small request/response scheme over UDP port 4000:

    request:  b"mobile" + <cmd> <value> + b"\\r\\n"
    response: b"master" + <param> <payload...> <param> <payload...> ...

Every command this client sends is answered with a full status frame, so a
single round trip both applies the change and returns the resulting device
state. That is not true of the protocol as a whole -- some write commands act
without replying (see the note on CMD_MANUAL_SPEED below) -- but it holds for
the commands used here.

This replaces the ``pyEcovent`` package, which performed blocking socket I/O
with a 15 second timeout -- unusable from the Home Assistant event loop, where
an unreachable unit would stall everything else for the duration of the
timeout. It also had no retries, no typed errors, and closed its socket only on
the success path.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 4000
DEFAULT_TIMEOUT = 5.0
DEFAULT_RETRIES = 3

REQUEST_HEADER = b"mobile"
REQUEST_FOOTER = b"\r\n"
RESPONSE_HEADER = b"master"
_HEADER_LEN = len(RESPONSE_HEADER)

CMD_STATUS = 0x01
CMD_TOGGLE_POWER = 0x03
CMD_SPEED = 0x04
CMD_MANUAL_SPEED = 0x05
CMD_AIRFLOW = 0x06
# Resets the filter replacement timer. Found by probing the undocumented gaps in
# the parameter space against real hardware: 0x1E answers and clears the filter
# end-of-life flag (0x12) from 1 to 0. Note it is *not* the same id as the
# filter parameter itself -- writing to 0x12 is ignored with every value.
CMD_RESET_FILTER = 0x1E

# The command byte is usually the parameter id with the payload as the new
# value, but the two spaces are not interchangeable, and a command that acts
# does not necessarily answer: 0x05 (manual speed) and 0x0B (humidity
# threshold) both apply silently. Never infer "no response" as "no effect".

SPEED_LOW = 1
SPEED_MEDIUM = 2
SPEED_HIGH = 3
SPEED_MANUAL = 4

AIRFLOW_VENTILATION = 0
AIRFLOW_HEAT_RECOVERY = 1
AIRFLOW_AIR_SUPPLY = 2

# Manual speed is a raw duty value written with CMD_MANUAL_SPEED. No entity
# drives it yet -- these are kept as the protocol reference for a future number
# entity, since the range is not derivable from anything else.
MIN_MANUAL_SPEED = 22
MAX_MANUAL_SPEED = 255

# Wire parameter id -> (payload length in bytes, name).
# The payload length is what lets us walk the frame, so an unknown id means we
# can no longer find the next parameter boundary and must stop parsing.
_PARAMS: dict[int, tuple[int, str]] = {
    0x03: (1, "state"),
    0x04: (1, "speed"),
    0x05: (1, "manual_speed"),
    0x06: (1, "airflow"),
    0x08: (1, "humidity"),
    0x09: (1, "operation_mode"),
    0x0B: (1, "humidity_sensor_threshold"),
    0x0C: (1, "alarm_status"),
    0x0D: (1, "relay_sensor_status"),
    0x0E: (3, "party_or_night_mode_countdown"),
    0x0F: (3, "night_mode_timer"),
    0x10: (3, "party_mode_timer"),
    0x11: (3, "deactivation_timer"),
    0x12: (1, "filter_eol_timer"),
    0x13: (1, "humidity_sensor_status"),
    0x14: (1, "boost_mode"),
    0x15: (1, "humidity_sensor"),
    0x16: (1, "relay_sensor"),
    0x17: (1, "sensor_10v"),
    0x19: (1, "sensor_10v_threshold"),
    0x1A: (1, "sensor_10v_status"),
    0x1B: (32, "slave_device_search"),
    0x1C: (4, "response_slave_search"),
    0x1F: (1, "cloud_activation"),
    0x25: (1, "sensor_10v_current_status"),
}


class EcoventError(Exception):
    """Base error for all fan communication problems."""


class EcoventConnectionError(EcoventError):
    """The fan could not be reached."""


class EcoventTimeoutError(EcoventConnectionError):
    """The fan did not answer in time."""


class EcoventProtocolError(EcoventError):
    """The fan answered with something we cannot parse."""


@dataclass(frozen=True, slots=True)
class EcoventState:
    """Decoded status frame.

    Any field may be ``None`` when the fan did not report that parameter --
    callers must never assume a value is present.
    """

    raw: dict[str, int]

    @property
    def is_on(self) -> bool | None:
        """Return whether the fan is running, or None if not reported."""
        state = self.raw.get("state")
        if state is None:
            return None
        return state == 1

    @property
    def speed(self) -> int | None:
        """Return the speed step (1-3), 4 for manual, or None."""
        return self.raw.get("speed")

    @property
    def manual_speed(self) -> int | None:
        """Return the raw manual speed (22-255), or None."""
        return self.raw.get("manual_speed")

    @property
    def airflow(self) -> int | None:
        """Return the airflow direction (0-2), or None."""
        return self.raw.get("airflow")

    @property
    def humidity(self) -> int | None:
        """Return the measured relative humidity in percent, or None."""
        return self.raw.get("humidity")

    @property
    def alarm(self) -> bool | None:
        """Return whether the unit is reporting an alarm."""
        value = self.raw.get("alarm_status")
        return None if value is None else bool(value)

    @property
    def boost_mode(self) -> bool | None:
        """Return whether boost mode is active."""
        value = self.raw.get("boost_mode")
        return None if value is None else bool(value)

    @property
    def filter_replacement_required(self) -> bool | None:
        """Return whether the filter needs replacing.

        Confirmed against a unit whose own "replace filter" LED was lit while
        this parameter read 1.
        """
        value = self.raw.get("filter_eol_timer")
        return None if value is None else bool(value)


def parse_response(data: bytes) -> EcoventState:
    """Decode a status frame into an :class:`EcoventState`.

    Unknown parameter ids abort the walk rather than raising, so firmware that
    reports extra parameters degrades to partial data instead of breaking the
    integration.
    """
    if len(data) <= _HEADER_LEN:
        raise EcoventProtocolError(f"Response too short: {data!r}")

    if not data.startswith(RESPONSE_HEADER):
        # Not fatal -- slave units have been reported to use other headers.
        _LOGGER.debug("Unexpected response header: %r", data[:_HEADER_LEN])

    body = data[_HEADER_LEN:]
    values: dict[str, int] = {}
    index = 0
    while index < len(body):
        param = body[index]
        if param not in _PARAMS:
            _LOGGER.debug(
                "Unknown parameter 0x%02x at offset %d, stopping parse of %r",
                param,
                index,
                body,
            )
            break
        length, name = _PARAMS[param]
        payload = body[index + 1 : index + 1 + length]
        if len(payload) < length:
            _LOGGER.debug("Truncated payload for parameter %s in %r", name, body)
            break
        # Every parameter we act on is single byte. The 3 byte ones are timers
        # encoded as big-endian seconds -- a real unit reported 28800, 14400 and
        # 600, i.e. exactly 8h, 4h and 10min. They are kept for diagnostics.
        values[name] = payload[0] if length == 1 else int.from_bytes(payload, "big")
        index += 1 + length

    if not values:
        raise EcoventProtocolError(f"No parameters decoded from {data!r}")

    return EcoventState(raw=values)


class _EcoventProtocol(asyncio.DatagramProtocol):
    """Resolve a future with the first datagram received."""

    def __init__(self) -> None:
        self.future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc: Exception) -> None:
        # On a connected UDP socket this surfaces ICMP errors such as port
        # unreachable, which lets us fail fast instead of waiting for a timeout.
        if not self.future.done():
            self.future.set_exception(EcoventConnectionError(str(exc)))

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None and not self.future.done():
            self.future.set_exception(EcoventConnectionError(str(exc)))


class EcoventFan:
    """Async client for a single ventilation unit."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retries = max(1, retries)
        # UDP has no ordering guarantee between concurrent exchanges, and a
        # power toggle is a read-modify-write, so serialize every exchange.
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the fan host."""
        return self._host

    async def _exchange(self, command: int, value: int) -> EcoventState:
        """Send one command and return the status frame it answers with."""
        async with self._lock:
            return await self._exchange_locked(command, value)

    async def _exchange_locked(self, command: int, value: int) -> EcoventState:
        """Do one request/response cycle. The caller must hold the lock."""
        packet = REQUEST_HEADER + bytes([command, value]) + REQUEST_FOOTER
        loop = asyncio.get_running_loop()
        last_error: Exception | None = None

        for attempt in range(1, self._retries + 1):
            transport = None
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    _EcoventProtocol, remote_addr=(self._host, self._port)
                )
                transport.sendto(packet)
                data = await asyncio.wait_for(protocol.future, self._timeout)
                # Parsed inside the try so a corrupted datagram is retried like
                # any other transport failure rather than aborting the poll.
                state = parse_response(data)
            except TimeoutError as err:
                last_error = EcoventTimeoutError(
                    f"No response from {self._host}:{self._port}"
                )
                last_error.__cause__ = err
                _LOGGER.debug(
                    "Timeout talking to %s (attempt %d/%d)",
                    self._host,
                    attempt,
                    self._retries,
                )
            # TimeoutError subclasses OSError, so it must be caught first.
            except OSError as err:
                last_error = EcoventConnectionError(
                    f"Error talking to {self._host}:{self._port}: {err}"
                )
                last_error.__cause__ = err
                _LOGGER.debug(
                    "Socket error talking to %s (attempt %d/%d): %s",
                    self._host,
                    attempt,
                    self._retries,
                    err,
                )
            except (EcoventConnectionError, EcoventProtocolError) as err:
                last_error = err
                _LOGGER.debug(
                    "Error talking to %s (attempt %d/%d): %s",
                    self._host,
                    attempt,
                    self._retries,
                    err,
                )
            else:
                return state
            finally:
                if transport is not None:
                    transport.close()

        raise last_error or EcoventConnectionError(
            f"Could not reach {self._host}:{self._port}"
        )

    async def async_update(self) -> EcoventState:
        """Poll the current status."""
        return await self._exchange(CMD_STATUS, 0x00)

    async def async_set_speed(self, speed: int) -> EcoventState:
        """Set the speed step (1-3)."""
        if not SPEED_LOW <= speed <= SPEED_HIGH:
            raise ValueError(f"Speed must be {SPEED_LOW}-{SPEED_HIGH}, got {speed}")
        return await self._exchange(CMD_SPEED, speed)


    async def async_set_airflow(self, airflow: int) -> EcoventState:
        """Set the airflow direction (0-2)."""
        if not AIRFLOW_VENTILATION <= airflow <= AIRFLOW_AIR_SUPPLY:
            raise ValueError(f"Airflow must be 0-2, got {airflow}")
        return await self._exchange(CMD_AIRFLOW, airflow)

    async def async_reset_filter_timer(self) -> EcoventState:
        """Tell the unit its filter has been replaced.

        Verified against real hardware: the unit answers with a status frame in
        which the filter end-of-life flag has gone from 1 to 0.
        """
        return await self._exchange(CMD_RESET_FILTER, 0x00)

    async def async_set_power(self, on: bool) -> EcoventState:
        """Turn the fan on or off.

        The device only exposes a *toggle*, so read the current state first and
        send the toggle only when it actually differs from the target. The lock
        is held across both steps: releasing it in between would let two
        concurrent calls each read "on" and each send a toggle, flipping the
        unit twice.
        """
        async with self._lock:
            state = await self._exchange_locked(CMD_STATUS, 0x00)
            if state.is_on is on:
                return state
            return await self._exchange_locked(CMD_TOGGLE_POWER, 0x00)
