"""Fixtures for the NIBE DVC tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nibe_dvc.api import (
    _PARAMS,
    REQUEST_HEADER,
    RESPONSE_HEADER,
    NibeDvcConfig,
    NibeDvcNetwork,
    NibeDvcState,
)
from custom_components.nibe_dvc.const import DOMAIN

# Addresses come from the RFC 5737 documentation range (192.0.2.0/24), which is
# reserved for examples and is guaranteed never to be a real host. Never put a
# real LAN address here -- it would publish your network layout. Tests that need
# real hardware read NIBE_DVC_TEST_HOST from the environment instead; see
# test_live_device.py.
TEST_HOST = "192.0.2.5"
TEST_PORT = 4000
TEST_NAME = "Basement fan"

# A real status frame captured from a Vents unit:
# 6d6173746572 0301 0900 0c00 1300 0d00 1a00 0401 05ff 0600 0837
# 0e000000 1201 1400 2500
REAL_FRAME = bytes.fromhex(
    "6d6173746572030109000c0013000d001a00040105ff060008370e000000120114002500"
)

# A real config frame, exactly as decoded in PROTOCOL.md.
REAL_CONFIG_FRAME = bytes.fromhex(
    "6d61737465720b4b1501160117000f007080100038401100025819321f01"
)


def status_frame(**values: int) -> bytes:
    """Build a status frame carrying the named parameters."""
    return _frame({"state": 1, "speed": 1, **values})


def config_frame(**values: int) -> bytes:
    """Build a config frame carrying the named parameters."""
    defaults = {
        "humidity_sensor_threshold": 75,
        "humidity_sensor": 1,
        "relay_sensor": 1,
        "sensor_10v": 0,
        "deactivation_timer": 600,
        "cloud_activation": 1,
    }
    return _frame({**defaults, **values})


def _frame(values: dict[str, int]) -> bytes:
    """Encode parameters back onto the wire the way the unit does."""
    by_name = {name: (param, size) for param, (size, name) in _PARAMS.items()}
    body = bytearray()
    for name, value in values.items():
        param, size = by_name[name]
        body.append(param)
        body += value.to_bytes(size, "big")
    return RESPONSE_HEADER + bytes(body)


class FakeUnit:
    """A scripted ventilation unit spliced in at the datagram endpoint.

    Lets the protocol client be exercised for real -- retries, the power toggle
    read-modify-write, the silent config writes -- none of which the AsyncMock
    in ``mock_fan`` can reach, because it replaces the client wholesale.

    ``handler`` receives each request packet and returns the reply bytes, or
    None to model a unit that stays silent (which is what the config writes do,
    and what a dropped datagram looks like from here).
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, handler) -> None:
        """Patch the running loop so every endpoint reaches this fake."""
        self.requests: list[bytes] = []
        self.protocols: list = []
        self._handler = handler
        monkeypatch.setattr(
            asyncio.get_running_loop(), "create_datagram_endpoint", self._endpoint
        )

    @property
    def commands(self) -> list[int]:
        """Return the command byte of every request received, in order."""
        return [request[len(REQUEST_HEADER)] for request in self.requests]

    async def _endpoint(self, factory, remote_addr=None):
        protocol = factory()
        self.protocols.append(protocol)
        unit = self

        class Transport:
            def sendto(self, data: bytes) -> None:
                unit.requests.append(data)
                if (reply := unit._handler(data)) is not None:
                    protocol.datagram_received(reply, remote_addr)

            def close(self) -> None:
                pass

        return Transport(), protocol


def make_state(**overrides: int | None) -> NibeDvcState:
    """Build an NibeDvcState, defaulting to "on, low, ventilation"."""
    raw: dict[str, int] = {
        "state": 1,
        "speed": 1,
        "manual_speed": 255,
        "airflow": 0,
        "humidity": 55,
        "alarm_status": 0,
        "boost_mode": 0,
        "filter_eol_timer": 0,
        # Trigger flags a real unit always reports, even when the matching
        # input is disabled.
        "humidity_sensor_status": 0,
        "relay_sensor_status": 0,
        "sensor_10v_status": 0,
        "operation_mode": 0,
        "sensor_10v_current_status": 0,
    }
    for key, value in overrides.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return NibeDvcState(raw=raw)


def make_config(**overrides: int | None) -> NibeDvcConfig:
    """Build an NibeDvcConfig matching a real unit's settings."""
    raw: dict[str, int] = {
        "humidity_sensor_threshold": 75,
        "humidity_sensor": 1,
        "relay_sensor": 1,
        "sensor_10v": 0,
        "night_mode_timer": 28800,
        "party_mode_timer": 14400,
        "deactivation_timer": 600,
        "sensor_10v_threshold": 50,
        "cloud_activation": 1,
    }
    for key, value in overrides.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return NibeDvcConfig(raw=raw)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    return


@pytest.fixture
def mock_fan():
    """Patch the UDP client with an AsyncMock that returns canned states."""
    fan = AsyncMock()
    fan.host = TEST_HOST
    fan.port = TEST_PORT
    fan.async_update.return_value = make_state()
    fan.async_set_speed.return_value = make_state(speed=2)
    fan.async_set_airflow.return_value = make_state(airflow=1)
    fan.async_set_power.return_value = make_state()
    fan.async_reset_filter_timer.return_value = make_state(filter_eol_timer=0)
    fan.async_get_config.return_value = make_config()
    fan.async_set_humidity_threshold.return_value = make_config(
        humidity_sensor_threshold=60
    )
    fan.async_set_deactivation_delay.return_value = make_config(deactivation_timer=1800)
    fan.async_get_network.return_value = NibeDvcNetwork(
        ssid="test-wifi", ip_address=TEST_HOST
    )

    with (
        patch("custom_components.nibe_dvc.NibeDvcFan", return_value=fan),
        patch("custom_components.nibe_dvc.config_flow.NibeDvcFan", return_value=fan),
    ):
        yield fan


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for the integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={CONF_HOST: TEST_HOST, CONF_PORT: TEST_PORT, CONF_NAME: TEST_NAME},
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fan
) -> MockConfigEntry:
    """Set up the integration and return its config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
