"""Number platform for the NIBE DVC integration.

These are the two settings that govern boost: the humidity level that triggers
it, and how long the unit keeps running at maximum speed once the trigger has
cleared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NibeDvcConfigEntry
from .api import (
    MAX_DEACTIVATION_DELAY,
    MAX_HUMIDITY_THRESHOLD,
    MIN_DEACTIVATION_DELAY,
    MIN_HUMIDITY_THRESHOLD,
    NibeDvcConfig,
    NibeDvcFan,
)
from .entity import NibeDvcEntity


@dataclass(frozen=True, kw_only=True)
class NibeDvcNumberEntityDescription(NumberEntityDescription):
    """Describes an NIBE DVC number."""

    value_fn: Callable[[NibeDvcConfig], int | None]
    set_fn: Callable[[NibeDvcFan, int], Awaitable[NibeDvcConfig]]


NUMBERS: tuple[NibeDvcNumberEntityDescription, ...] = (
    NibeDvcNumberEntityDescription(
        key="humidity_sensor_threshold",
        translation_key="humidity_threshold",
        device_class=NumberDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=MIN_HUMIDITY_THRESHOLD,
        native_max_value=MAX_HUMIDITY_THRESHOLD,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda config: config.humidity_threshold,
        set_fn=lambda fan, value: fan.async_set_humidity_threshold(value),
    ),
    NibeDvcNumberEntityDescription(
        key="deactivation_timer",
        translation_key="boost_run_on",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=NumberDeviceClass.DURATION,
        native_min_value=MIN_DEACTIVATION_DELAY,
        native_max_value=MAX_DEACTIVATION_DELAY,
        native_step=60,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda config: config.deactivation_delay,
        set_fn=lambda fan, value: fan.async_set_deactivation_delay(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NibeDvcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NIBE DVC numbers from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.config.raw if coordinator.config is not None else {}

    async_add_entities(
        NibeDvcNumber(entry, description)
        for description in NUMBERS
        if description.key in reported
    )


class NibeDvcNumber(NibeDvcEntity, NumberEntity):
    """A writable setting on the ventilation unit."""

    entity_description: NibeDvcNumberEntityDescription

    def __init__(
        self,
        entry: NibeDvcConfigEntry,
        description: NibeDvcNumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            entry.runtime_data, entry.entry_id, entry.title, description.key
        )
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return True only once the settings have actually been read."""
        return super().available and self.coordinator.config is not None

    @property
    def native_value(self) -> float | None:
        """Return the current setting."""
        config = self.coordinator.config
        if config is None:
            return None
        return self.entity_description.value_fn(config)

    async def async_set_native_value(self, value: float) -> None:
        """Write the setting to the unit."""
        fan = self.coordinator.fan
        await self.coordinator.async_execute_config(
            lambda: self.entity_description.set_fn(fan, int(value))
        )
