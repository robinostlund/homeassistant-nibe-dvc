"""The NIBE DVC integration for Vents/Blauberg TwinFresh ventilation units."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .api import DEFAULT_PORT, NibeDvcFan
from .const import DOMAIN
from .coordinator import NibeDvcDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SENSOR,
]

type NibeDvcConfigEntry = ConfigEntry[NibeDvcDataUpdateCoordinator]

# This integration is configured entirely from the UI. The schema alone is what
# reports a leftover YAML block to the user and ignores it -- no async_setup is
# needed, Home Assistant sets the integration up from its config entries.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: NibeDvcConfigEntry) -> bool:
    """Set up NIBE DVC from a config entry."""
    fan = NibeDvcFan(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = NibeDvcDataUpdateCoordinator(hass, entry, fan)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NibeDvcConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
