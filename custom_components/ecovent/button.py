"""Button platform for the EcoVent integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoventConfigEntry
from .entity import EcoventEntity

RESET_FILTER = ButtonEntityDescription(
    key="reset_filter",
    translation_key="reset_filter",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcoventConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EcoVent buttons from a config entry."""
    coordinator = entry.runtime_data
    reported = coordinator.data.raw if coordinator.data is not None else {}

    # Only offer the reset if the unit actually tracks a filter timer.
    if "filter_eol_timer" in reported:
        async_add_entities([EcoventResetFilterButton(entry)])


class EcoventResetFilterButton(EcoventEntity, ButtonEntity):
    """Tell the unit its filter has been replaced."""

    entity_description = RESET_FILTER

    def __init__(self, entry: EcoventConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(
            entry.runtime_data, entry.entry_id, entry.title, RESET_FILTER.key
        )

    async def async_press(self) -> None:
        """Reset the filter replacement timer."""
        fan = self.coordinator.fan
        await self.coordinator.async_execute(fan.async_reset_filter_timer)
