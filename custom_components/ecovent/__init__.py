"""The EcoVent integration for Vents/Blauberg TwinFresh ventilation units."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import EcoventFan
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import EcoventDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.FAN,
    Platform.SENSOR,
]

type EcoventConfigEntry = ConfigEntry[EcoventDataUpdateCoordinator]

# This integration is configured entirely from the UI.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration; there is nothing to do for YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EcoventConfigEntry) -> bool:
    """Set up EcoVent from a config entry."""
    fan = EcoventFan(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = EcoventDataUpdateCoordinator(hass, entry, fan)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcoventConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
