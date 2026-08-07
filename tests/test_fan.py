"""Tests for the EcoVent fan platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
    FanEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ecovent.api import EcoventTimeoutError

from .conftest import make_state

ENTITY_ID = "fan.basement_fan"


async def test_entity_created(hass: HomeAssistant, setup_integration) -> None:
    """The fan entity is created with a unique id and device."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON

    entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == setup_integration.entry_id
    assert entry.device_id is not None


async def test_supported_features(hass: HomeAssistant, setup_integration) -> None:
    """TURN_ON and TURN_OFF must be declared explicitly.

    Home Assistant removed the implicit fallback, so a fan without these flags
    loses its on/off controls.
    """
    features = hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES]

    assert features & FanEntityFeature.TURN_ON
    assert features & FanEntityFeature.TURN_OFF
    assert features & FanEntityFeature.SET_SPEED
    assert features & FanEntityFeature.PRESET_MODE


async def test_preset_modes_listed(hass: HomeAssistant, setup_integration) -> None:
    """The airflow directions are exposed as preset modes."""
    attrs = hass.states.get(ENTITY_ID).attributes

    assert attrs[ATTR_PRESET_MODES] == [
        "ventilation",
        "heat_recovery",
        "air_supply",
    ]
    assert attrs[ATTR_PRESET_MODE] == "ventilation"


@pytest.mark.parametrize(
    ("raw_state", "expected_percentage"),
    [
        ({"speed": 1}, 33),
        ({"speed": 2}, 66),
        ({"speed": 3}, 100),
        # Off reports 0 regardless of the speed the unit remembers.
        ({"state": 0, "speed": 3}, 0),
        # Manual mode is a raw 22-255 duty value.
        ({"speed": 4, "manual_speed": 255}, 100),
        ({"speed": 4, "manual_speed": 138}, 50),
        # Never report 0 for a running fan; that would read as off.
        ({"speed": 4, "manual_speed": 22}, 1),
    ],
)
async def test_percentage_mapping(
    hass: HomeAssistant,
    config_entry,
    mock_fan: AsyncMock,
    raw_state: dict,
    expected_percentage: int,
) -> None:
    """Speeds map to percentages, including the manual mode the old code crashed on."""
    mock_fan.async_update.return_value = make_state(**raw_state)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes[ATTR_PERCENTAGE] == expected_percentage


@pytest.mark.parametrize(
    "raw_state",
    [
        {"speed": None},  # parameter absent entirely
        {"speed": 9},  # value outside anything we know
        {"speed": 4, "manual_speed": None},  # manual mode without a duty value
    ],
)
async def test_unmappable_speed_reports_none(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock, raw_state: dict
) -> None:
    """An unmappable speed yields None instead of raising.

    The old code called ordered_list_item_to_percentage() directly, which raised
    ValueError for "manual"/"unknown" and broke the whole state write.
    """
    mock_fan.async_update.return_value = make_state(**raw_state)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] is None


async def test_state_off(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """A stopped fan reports off, not on.

    The old is_on returned the raw string "off", which is truthy.
    """
    mock_fan.async_update.return_value = make_state(state=0)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_turn_on_and_off(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Turn on/off drive the power command."""
    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    mock_fan.async_set_power.assert_awaited_with(True)

    mock_fan.async_set_power.return_value = make_state(state=0)
    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    mock_fan.async_set_power.assert_awaited_with(False)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_turn_on_with_percentage(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """turn_on with a percentage actually applies the speed.

    The old code called self.async_set_percentage(...) without awaiting it, so
    the speed was never sent.
    """
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: 66},
        blocking=True,
    )

    mock_fan.async_set_speed.assert_awaited_once_with(2)


@pytest.mark.parametrize(
    ("percentage", "expected_speed"),
    [(1, 1), (33, 1), (34, 2), (66, 2), (67, 3), (100, 3)],
)
async def test_set_percentage(
    hass: HomeAssistant,
    setup_integration,
    mock_fan: AsyncMock,
    percentage: int,
    expected_speed: int,
) -> None:
    """Percentages map onto the three speed steps."""
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: percentage},
        blocking=True,
    )

    mock_fan.async_set_speed.assert_awaited_once_with(expected_speed)


async def test_set_percentage_zero_turns_off(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """Setting 0% powers the unit down rather than sending an invalid speed."""
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: 0},
        blocking=True,
    )

    mock_fan.async_set_power.assert_awaited_once_with(False)
    mock_fan.async_set_speed.assert_not_awaited()


async def test_set_percentage_powers_on_first(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Setting a speed on a stopped unit powers it on first."""
    mock_fan.async_update.return_value = make_state(state=0)
    mock_fan.async_set_power.return_value = make_state(state=0)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: 100},
        blocking=True,
    )

    mock_fan.async_set_power.assert_awaited_once_with(True)
    mock_fan.async_set_speed.assert_awaited_once_with(3)


async def test_set_preset_mode(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """The standard preset mode service sets the airflow direction."""
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "heat_recovery"},
        blocking=True,
    )

    mock_fan.async_set_airflow.assert_awaited_once_with(1)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_PRESET_MODE] == "heat_recovery"




async def test_becomes_unavailable_on_error(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """A failed poll marks the entity unavailable instead of serving stale data."""
    mock_fan.async_update.side_effect = EcoventTimeoutError("no response")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_command_error_surfaces(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """A failed command raises a HomeAssistantError the user can see."""
    mock_fan.async_set_power.side_effect = EcoventTimeoutError("no response")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )


async def test_unload(hass: HomeAssistant, setup_integration) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_percentage_is_100_while_boosting(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Boost runs the unit at maximum speed while `speed` still reads low.

    The manual is explicit that a triggered sensor drives the unit to maximum
    speed and it returns to the *previous* speed afterwards, so the speed
    parameter keeps reporting the configured step throughout. Reporting 33%
    while the fan is flat out would be wrong.
    """
    mock_fan.async_update.return_value = make_state(speed=1, boost_mode=1)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes[ATTR_PERCENTAGE] == 100


async def test_percentage_is_100_during_boost_run_on(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Boost value 2 is the run-on countdown, still at maximum speed."""
    mock_fan.async_update.return_value = make_state(speed=1, boost_mode=2)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes[ATTR_PERCENTAGE] == 100
