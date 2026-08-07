"""Binary sensor platform for the NIBE DVC integration."""

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

from . import NibeDvcConfigEntry
from .api import NibeDvcState
from .entity import NibeDvcEntity


@dataclass(frozen=True, kw_only=True)
class NibeDvcBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an NIBE DVC binary sensor."""

    value_fn: Callable[[NibeDvcState], bool | None]
    # Config key that must be enabled for this input to be wired up at all.
    requires_enabled: str | None = None


BINARY_SENSORS: tuple[NibeDvcBinarySensorEntityDescription, ...] = (
    NibeDvcBinarySensorEntityDescription(
        key="alarm_status",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.alarm,
    ),
    NibeDvcBinarySensorEntityDescription(
        key="boost_mode",
        translation_key="boost_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.boost_mode,
    ),
    NibeDvcBinarySensorEntityDescription(
        key="humidity_sensor_status",
        translation_key="humidity_trigger",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.humidity_trigger,
        requires_enabled="humidity_sensor",
    ),
    NibeDvcBinarySensorEntityDescription(
        key="relay_sensor_status",
        translation_key="relay_trigger",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.relay_trigger,
        requires_enabled="relay_sensor",
    ),
    NibeDvcBinarySensorEntityDescription(
        key="sensor_10v_status",
        translation_key="sensor_10v_trigger",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.sensor_10v_trigger,
        requires_enabled="sensor_10v",
    ),
    NibeDvcBinarySensorEntityDescription(
        key="filter_eol_timer",
        translation_key="filter",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.filter_replacement_required,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NibeDvcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NIBE DVC binary sensors from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.data.raw if coordinator.data is not None else {}
    config = coordinator.config.raw if coordinator.config is not None else {}

    def wanted(description: NibeDvcBinarySensorEntityDescription) -> bool:
        if description.key not in reported:
            return False
        # An input the installer has not enabled would sit at "off" forever.
        if description.requires_enabled is not None:
            return bool(config.get(description.requires_enabled))
        return True

    async_add_entities(
        NibeDvcBinarySensor(entry, description)
        for description in BINARY_SENSORS
        if wanted(description)
    )


class NibeDvcBinarySensor(NibeDvcEntity, BinarySensorEntity):
    """A boolean status flag reported by the ventilation unit."""

    entity_description: NibeDvcBinarySensorEntityDescription

    def __init__(
        self,
        entry: NibeDvcConfigEntry,
        description: NibeDvcBinarySensorEntityDescription,
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
