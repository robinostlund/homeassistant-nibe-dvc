"""Fan platform for the EcoVent integration."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from . import EcoventConfigEntry
from .api import SPEED_MANUAL
from .const import (
    AIRFLOW_TO_PRESET_MODE,
    MANUAL_SPEED_RANGE,
    PRESET_MODE_TO_AIRFLOW,
    PRESET_MODES,
    SPEED_RANGE,
)
from .entity import EcoventEntity

SPEED_COUNT = SPEED_RANGE[1] - SPEED_RANGE[0] + 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoventConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EcoVent fan from a config entry."""
    async_add_entities([EcoventFanEntity(entry)])


class EcoventFanEntity(EcoventEntity, FanEntity):
    """Representation of a Vents/Blauberg ventilation unit."""

    _attr_name = None
    _attr_translation_key = "ecovent"
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = SPEED_COUNT
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, entry: EcoventConfigEntry) -> None:
        """Initialize the fan."""
        super().__init__(entry.runtime_data, entry.entry_id, entry.title)

    @property
    def is_on(self) -> bool | None:
        """Return whether the fan is running."""
        if (data := self.data) is None:
            return None
        return data.is_on

    @property
    def percentage(self) -> int | None:
        """Return the current speed as a percentage.

        Returns None rather than raising when the fan reports a speed we cannot
        map, so an unexpected value never breaks the state write.
        """
        if (data := self.data) is None:
            return None
        if not data.is_on:
            return 0
        if data.boost_mode:
            # A triggered sensor drives the unit to maximum speed while `speed`
            # keeps reporting the configured step, so trust boost over speed.
            return 100

        speed = data.speed
        if speed is not None and SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]:
            return ranged_value_to_percentage(SPEED_RANGE, speed)
        if speed == SPEED_MANUAL and data.manual_speed is not None:
            # Manual mode is a raw 22-255 duty value; never report 0 for a
            # running fan, that would read as "off".
            return max(
                1, ranged_value_to_percentage(MANUAL_SPEED_RANGE, data.manual_speed)
            )
        return None

    @property
    def preset_mode(self) -> str | None:
        """Return the current airflow direction."""
        if (data := self.data) is None:
            return None
        return AIRFLOW_TO_PRESET_MODE.get(data.airflow)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        fan = self.coordinator.fan

        if percentage == 0:
            await self.coordinator.async_execute(lambda: fan.async_set_power(False))
            return

        speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        speed = min(max(speed, SPEED_RANGE[0]), SPEED_RANGE[1])

        # Setting a speed does not power the unit on, so do that first.
        if (data := self.data) is None or not data.is_on:
            await self.coordinator.async_execute(lambda: fan.async_set_power(True))

        await self.coordinator.async_execute(lambda: fan.async_set_speed(speed))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the airflow direction."""
        fan = self.coordinator.fan
        airflow = PRESET_MODE_TO_AIRFLOW[preset_mode]
        await self.coordinator.async_execute(lambda: fan.async_set_airflow(airflow))

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on.

        Without an explicit percentage the unit keeps whatever speed it was last
        set to, which is what the physical controls do too.
        """
        fan = self.coordinator.fan
        await self.coordinator.async_execute(lambda: fan.async_set_power(True))

        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        if percentage is not None:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        fan = self.coordinator.fan
        await self.coordinator.async_execute(lambda: fan.async_set_power(False))
