"""Tests for the NIBE DVC number platform — the two boost settings."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.nibe_dvc.api import NibeDvcTimeoutError

from .conftest import make_config

THRESHOLD = "number.basement_fan_boost_humidity_threshold"
RUN_ON = "number.basement_fan_boost_run_on_time"


async def test_numbers_created(hass: HomeAssistant, setup_integration) -> None:
    """Both boost settings are exposed as config entities."""
    threshold = hass.states.get(THRESHOLD)
    run_on = hass.states.get(RUN_ON)

    assert threshold is not None
    assert float(threshold.state) == 75
    assert threshold.attributes["min"] == 40
    assert threshold.attributes["max"] == 80

    assert run_on is not None
    assert float(run_on.state) == 600
    assert run_on.attributes["max"] == 86400

    registry = er.async_get(hass)
    assert registry.async_get(THRESHOLD).entity_category == "config"
    assert registry.async_get(RUN_ON).entity_category == "config"


async def test_set_humidity_threshold(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Writing the threshold sends it and reflects the confirmed value."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: THRESHOLD, ATTR_VALUE: 60},
        blocking=True,
    )

    mock_fan.async_set_humidity_threshold.assert_awaited_once_with(60)
    # The unit applies config writes silently, so the api re-reads to confirm.
    assert float(hass.states.get(THRESHOLD).state) == 60


async def test_set_boost_run_on(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Writing the run-on delay sends whole seconds."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: RUN_ON, ATTR_VALUE: 1800},
        blocking=True,
    )

    mock_fan.async_set_deactivation_delay.assert_awaited_once_with(1800)
    assert float(hass.states.get(RUN_ON).state) == 1800


async def test_write_error_surfaces(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """A failed config write raises an error the user can see."""
    mock_fan.async_set_humidity_threshold.side_effect = NibeDvcTimeoutError("nope")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: THRESHOLD, ATTR_VALUE: 60},
            blocking=True,
        )


async def test_numbers_skipped_when_not_reported(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """A unit that does not report a setting gets no entity for it."""
    mock_fan.async_get_config.return_value = make_config(
        humidity_sensor_threshold=None, deactivation_timer=None
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(THRESHOLD) is None
    assert hass.states.get(RUN_ON) is None


async def test_unit_without_config_frame_still_works(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """A unit that will not answer the config command must still set up.

    The config command is undocumented and was found by probing, so a firmware
    that does not implement it is entirely plausible. It used to take the whole
    integration down with it -- no fan, no sensors, just a permanent retry loop.
    Losing it should cost only the settings that live in that frame.
    """
    mock_fan.async_get_config.side_effect = NibeDvcTimeoutError("no config frame")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("fan.basement_fan").state == STATE_ON
    assert hass.states.get("sensor.basement_fan_humidity").state == "55"
    assert hass.states.get("binary_sensor.basement_fan_filter") is not None
    # Only the config-frame entities are missing.
    assert hass.states.get(THRESHOLD) is None
    assert hass.states.get(RUN_ON) is None


async def test_numbers_go_unavailable_when_config_is_lost(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Losing the config frame mid-run must not serve a stale setting."""
    assert hass.states.get(THRESHOLD).state != STATE_UNAVAILABLE

    mock_fan.async_get_config.side_effect = NibeDvcTimeoutError("no config frame")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()

    assert hass.states.get(THRESHOLD).state == STATE_UNAVAILABLE
    # The fan keeps working -- the status frame is still arriving.
    assert hass.states.get("fan.basement_fan").state == STATE_ON
