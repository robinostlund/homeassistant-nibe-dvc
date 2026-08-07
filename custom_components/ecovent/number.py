"""Number platform for the EcoVent integration.

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

from . import EcoventConfigEntry
from .api import (
    MAX_DEACTIVATION_DELAY,
    MAX_HUMIDITY_THRESHOLD,
    MIN_DEACTIVATION_DELAY,
    MIN_HUMIDITY_THRESHOLD,
    EcoventConfig,
    EcoventFan,
)
from .entity import EcoventEntity


@dataclass(frozen=True, kw_only=True)
class EcoventNumberEntityDescription(NumberEntityDescription):
    """Describes an EcoVent number."""

    value_fn: Callable[[EcoventConfig], int | None]
    set_fn: Callable[[EcoventFan, int], Awaitable[EcoventConfig]]


NUMBERS: tuple[EcoventNumberEntityDescription, ...] = (
    EcoventNumberEntityDescription(
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
    EcoventNumberEntityDescription(
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
    entry: EcoventConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EcoVent numbers from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.config.raw if coordinator.config is not None else {}

    async_add_entities(
        EcoventNumber(entry, description)
        for description in NUMBERS
        if description.key in reported
    )


class EcoventNumber(EcoventEntity, NumberEntity):
    """A writable setting on the ventilation unit."""

    entity_description: EcoventNumberEntityDescription

    def __init__(
        self,
        entry: EcoventConfigEntry,
        description: EcoventNumberEntityDescription,
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
