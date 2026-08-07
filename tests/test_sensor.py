"""Tests for the EcoVent sensor and binary sensor platforms."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    PERCENTAGE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.ecovent.api import EcoventTimeoutError

from .conftest import make_state

HUMIDITY = "sensor.basement_fan_humidity"
ALARM = "binary_sensor.basement_fan_alarm"
BOOST = "binary_sensor.basement_fan_boost_mode"
FILTER = "binary_sensor.basement_fan_filter"


async def test_humidity_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Humidity is exposed as a proper measurement sensor."""
    state = hass.states.get(HUMIDITY)

    assert state is not None
    assert state.state == "55"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.HUMIDITY
    assert state.attributes["unit_of_measurement"] == PERCENTAGE
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


async def test_binary_sensors(hass: HomeAssistant, setup_integration) -> None:
    """Alarm and boost mode are exposed as binary sensors."""
    assert hass.states.get(ALARM).state == STATE_OFF
    assert hass.states.get(BOOST).state == STATE_OFF

    registry = er.async_get(hass)
    assert registry.async_get(ALARM).entity_category == "diagnostic"
    assert registry.async_get(BOOST).entity_category == "diagnostic"


async def test_alarm_reflects_device(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """A raised alarm flag shows as a problem."""
    mock_fan.async_update.return_value = make_state(alarm_status=1, boost_mode=1)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ALARM).state == STATE_ON
    assert hass.states.get(BOOST).state == STATE_ON


async def test_unique_ids_are_distinct(
    hass: HomeAssistant, setup_integration
) -> None:
    """Every entity of a unit gets its own unique id, all on one device."""
    registry = er.async_get(hass)
    entries = [
        registry.async_get(entity_id)
        for entity_id in ("fan.basement_fan", HUMIDITY, ALARM, BOOST, FILTER)
    ]

    unique_ids = {entry.unique_id for entry in entries}
    assert len(unique_ids) == 5
    assert len({entry.device_id for entry in entries}) == 1


async def test_sensors_skipped_when_not_reported(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Units that do not report a parameter do not get a phantom entity."""
    mock_fan.async_update.return_value = make_state(
        humidity=None, alarm_status=None, boost_mode=None, filter_eol_timer=None
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(HUMIDITY) is None
    assert hass.states.get(ALARM) is None
    assert hass.states.get(BOOST) is None
    assert hass.states.get(FILTER) is None
    # The fan itself is still there.
    assert hass.states.get("fan.basement_fan") is not None


async def test_sensors_go_unavailable(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Losing the unit marks every entity unavailable, not just the fan."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    mock_fan.async_update.side_effect = EcoventTimeoutError("no response")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()

    for entity_id in ("fan.basement_fan", HUMIDITY, ALARM, BOOST, FILTER):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


SSID = "sensor.basement_fan_wi_fi_network"


async def test_ssid_sensor(hass: HomeAssistant, setup_integration) -> None:
    """The unit's Wi-Fi network is exposed as a diagnostic sensor."""
    state = hass.states.get(SSID)

    assert state is not None
    assert state.state == "test-wifi"
    assert er.async_get(hass).async_get(SSID).entity_category == "diagnostic"


async def test_ssid_sensor_skipped_when_unreadable(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """A unit that will not report its network gets no Wi-Fi sensor.

    Reading network settings must never be able to fail the whole setup.
    """
    mock_fan.async_get_network.side_effect = EcoventTimeoutError("no response")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(SSID) is None
    assert hass.states.get("fan.basement_fan") is not None


HUM_TRIGGER = "binary_sensor.basement_fan_humidity_trigger"
RELAY_TRIGGER = "binary_sensor.basement_fan_external_sensor"
ANALOG_TRIGGER = "binary_sensor.basement_fan_analog_sensor"


async def test_trigger_sensors_follow_enabled_inputs(
    hass: HomeAssistant, setup_integration
) -> None:
    """Only inputs the installer enabled get an entity.

    A disabled input would sit at "off" forever, which reads as "all clear"
    rather than "not wired up". The test unit has humidity and relay enabled
    and the 0-10 V input disabled.
    """
    assert hass.states.get(HUM_TRIGGER) is not None
    assert hass.states.get(RELAY_TRIGGER) is not None
    assert hass.states.get(ANALOG_TRIGGER) is None


async def test_relay_trigger_reflects_device(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """An external sensor closing its contact shows up.

    This is how a CO2 sensor wired to NO1/NO2 reports - the unit gives a
    trigger flag, never a measured concentration.
    """
    mock_fan.async_update.return_value = make_state(relay_sensor_status=1)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(RELAY_TRIGGER).state == STATE_ON


async def test_analog_trigger_created_when_enabled(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Enabling the 0-10 V input creates its entity."""
    from .conftest import make_config

    mock_fan.async_get_config.return_value = make_config(sensor_10v=1)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ANALOG_TRIGGER) is not None
