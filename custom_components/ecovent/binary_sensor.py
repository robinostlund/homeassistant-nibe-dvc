"""Binary sensor platform for the EcoVent integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoventConfigEntry
from .api import EcoventState
from .entity import EcoventEntity


@dataclass(frozen=True, kw_only=True)
class EcoventBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an EcoVent binary sensor."""

    value_fn: Callable[[EcoventState], bool | None]


BINARY_SENSORS: tuple[EcoventBinarySensorEntityDescription, ...] = (
    EcoventBinarySensorEntityDescription(
        key="alarm_status",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.alarm,
    ),
    EcoventBinarySensorEntityDescription(
        key="boost_mode",
        translation_key="boost_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.boost_mode,
    ),
    EcoventBinarySensorEntityDescription(
        key="filter_eol_timer",
        translation_key="filter",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.filter_replacement_required,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoventConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EcoVent binary sensors from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.data.raw if coordinator.data is not None else {}

    async_add_entities(
        EcoventBinarySensor(entry, description)
        for description in BINARY_SENSORS
        if description.key in reported
    )


class EcoventBinarySensor(EcoventEntity, BinarySensorEntity):
    """A boolean status flag reported by the ventilation unit."""

    entity_description: EcoventBinarySensorEntityDescription

    def __init__(
        self,
        entry: EcoventConfigEntry,
        description: EcoventBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            entry.runtime_data, entry.entry_id, entry.title, description.key
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the current flag value."""
        if (data := self.data) is None:
            return None
        return self.entity_description.value_fn(data)
