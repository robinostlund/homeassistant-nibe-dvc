"""End-to-end tests against real hardware.

Skipped unless ECOVENT_TEST_HOST points at a reachable ventilation unit:

    ECOVENT_TEST_HOST=192.0.2.50 pytest tests/test_live_device.py

These tests are read-only -- they never change the state of the unit.
"""

from __future__ import annotations

import os

import pytest
import pytest_socket
from homeassistant.components.fan import ATTR_PERCENTAGE, ATTR_PRESET_MODE
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecovent.const import DOMAIN, PRESET_MODES

LIVE_HOST = os.environ.get("ECOVENT_TEST_HOST")
LIVE_PORT = int(os.environ.get("ECOVENT_TEST_PORT", "4000"))

pytestmark = pytest.mark.skipif(
    not LIVE_HOST, reason="ECOVENT_TEST_HOST is not set"
)


@pytest.fixture(autouse=True)
def allow_live_host(socket_enabled):
    """Allow real network access to the unit under test.

    The test harness pins the allowlist to 127.0.0.1 in ``pytest_runtest_setup``,
    which runs before fixtures, so widen it here.
    """
    pytest_socket.socket_allow_hosts([LIVE_HOST, "127.0.0.1"])
    return


@pytest.fixture(name="live_entry")
async def live_entry_fixture(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the integration against the real unit."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Live fan",
        data={CONF_HOST: LIVE_HOST, CONF_PORT: LIVE_PORT, CONF_NAME: "Live fan"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_live_entity_state(hass: HomeAssistant, live_entry) -> None:
    """The real unit produces a valid, fully populated fan state."""
    state = hass.states.get("fan.live_fan")

    assert state is not None
    assert state.state in (STATE_ON, STATE_OFF)
    assert state.attributes[ATTR_PRESET_MODE] in PRESET_MODES

    percentage = state.attributes[ATTR_PERCENTAGE]
    assert percentage is not None
    assert 0 <= percentage <= 100
    if state.state == STATE_OFF:
        assert percentage == 0


async def test_live_sensors(hass: HomeAssistant, live_entry) -> None:
    """The unit's sensors come up with plausible real readings."""
    humidity = hass.states.get("sensor.live_fan_humidity")
    assert humidity is not None
    assert 0 <= float(humidity.state) <= 100

    for entity_id in (
        "binary_sensor.live_fan_alarm",
        "binary_sensor.live_fan_boost_mode",
        "binary_sensor.live_fan_filter",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state in (STATE_ON, STATE_OFF)



async def test_live_diagnostics(hass: HomeAssistant, live_entry) -> None:
    """Diagnostics expose the raw parameters and redact the host."""
    from custom_components.ecovent.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, live_entry)

    assert diagnostics["last_update_success"] is True
    assert diagnostics["entry_data"][CONF_HOST] == "**REDACTED**"
    assert diagnostics["state"]["state"] in (0, 1)
