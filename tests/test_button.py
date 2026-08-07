"""Tests for the NIBE DVC button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.nibe_dvc.api import CMD_RESET_FILTER, NibeDvcTimeoutError

from .conftest import make_state

BUTTON = "button.basement_fan_reset_filter_timer"
FILTER = "binary_sensor.basement_fan_filter"


def test_reset_command_byte() -> None:
    """The reset command is 0x1E, not the filter parameter id 0x12.

    Writing to 0x12 is ignored by the unit with every value; 0x1E is the
    command that actually clears the flag. Verified against real hardware.
    """
    assert CMD_RESET_FILTER == 0x1E


async def test_button_created(hass: HomeAssistant, setup_integration) -> None:
    """The reset button is created as a config entity."""
    assert hass.states.get(BUTTON) is not None
    assert er.async_get(hass).async_get(BUTTON).entity_category == "config"


async def test_press_resets_filter(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Pressing the button clears the filter flag on the unit."""
    mock_fan.async_update.return_value = make_state(filter_eol_timer=1)
    mock_fan.async_reset_filter_timer.return_value = make_state(filter_eol_timer=0)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(FILTER).state == STATE_ON

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True
    )

    mock_fan.async_reset_filter_timer.assert_awaited_once()
    # The unit answers the reset with a full status frame, so the binary sensor
    # updates immediately rather than waiting for the next poll.
    assert hass.states.get(FILTER).state == STATE_OFF


async def test_press_error_surfaces(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """A failed reset raises an error the user can see."""
    mock_fan.async_reset_filter_timer.side_effect = NibeDvcTimeoutError("no response")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True
        )


async def test_button_skipped_without_filter_timer(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Units that do not report a filter timer get no reset button."""
    mock_fan.async_update.return_value = make_state(filter_eol_timer=None)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(BUTTON) is None
    assert hass.states.get(FILTER) is None
