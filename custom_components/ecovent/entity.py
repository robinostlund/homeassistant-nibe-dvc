"""Base entity shared by all EcoVent platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EcoventState
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import EcoventDataUpdateCoordinator


class EcoventEntity(CoordinatorEntity[EcoventDataUpdateCoordinator]):
    """Common device wiring and availability for every EcoVent entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcoventDataUpdateCoordinator,
        entry_id: str,
        device_name: str,
        key: str | None = None,
    ) -> None:
        """Initialize the entity.

        ``key`` is the per platform suffix of the unique id; the fan entity
        passes None because it represents the device itself.
        """
        super().__init__(coordinator)
        self._attr_unique_id = entry_id if key is None else f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            # The protocol exposes no serial number, so the config entry id is
            # the only stable identifier -- it survives the unit changing IP.
            identifiers={(DOMAIN, entry_id)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def data(self) -> EcoventState | None:
        """Return the latest state, or None if the unit never answered."""
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Return True only when the last poll succeeded and produced data.

        Guarding on the data being present matters: a property that assumes
        coordinator data exists will raise inside the state write and spam the
        log with tracebacks instead of simply showing the entity unavailable.
        """
        return super().available and self.coordinator.data is not None
