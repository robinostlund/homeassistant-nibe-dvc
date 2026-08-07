"""Sensor platform for the EcoVent integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoventConfigEntry
from .api import EcoventState
from .entity import EcoventEntity


@dataclass(frozen=True, kw_only=True)
class EcoventSensorEntityDescription(SensorEntityDescription):
    """Describes an EcoVent sensor."""

    value_fn: Callable[[EcoventState], int | None]


SENSORS: tuple[EcoventSensorEntityDescription, ...] = (
    EcoventSensorEntityDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.humidity,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoventConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EcoVent sensors from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.data.raw if coordinator.data is not None else {}

    # Not every unit has every sensor fitted, so only create entities for the
    # parameters this unit actually reports.
    entities: list[SensorEntity] = [
        EcoventSensor(entry, description)
        for description in SENSORS
        if description.key in reported
    ]
    if coordinator.network is not None and coordinator.network.ssid:
        entities.append(EcoventSsidSensor(entry))

    async_add_entities(entities)


class EcoventSsidSensor(EcoventEntity, SensorEntity):
    """The Wi-Fi network the unit is joined to.

    Read once when the entry is set up, so it follows a reload rather than the
    polling interval -- the value does not change while the unit stays online.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "ssid"

    def __init__(self, entry: EcoventConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, entry.title, "ssid")

    @property
    def native_value(self) -> str | None:
        """Return the SSID."""
        network = self.coordinator.network
        return None if network is None else network.ssid


class EcoventSensor(EcoventEntity, SensorEntity):
    """A measurement reported by the ventilation unit."""

    entity_description: EcoventSensorEntityDescription

    def __init__(
        self,
        entry: EcoventConfigEntry,
        description: EcoventSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            entry.runtime_data, entry.entry_id, entry.title, description.key
        )
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        """Return the current measurement."""
        if (data := self.data) is None:
            return None
        return self.entity_description.value_fn(data)
