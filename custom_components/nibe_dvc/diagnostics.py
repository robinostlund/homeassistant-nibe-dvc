"""Diagnostics support for the NIBE DVC integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import NibeDvcConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NibeDvcConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        # Raw wire parameters, including ones no entity exposes yet. Both frames
        # are dumped: the config frame is where the timers, the 0-10 V threshold
        # and the cloud flag live, none of which appear in the status frame.
        "state": coordinator.data.raw if coordinator.data is not None else None,
        "config": coordinator.config.raw if coordinator.config is not None else None,
        # Deliberately no network settings: that frame carries the Wi-Fi
        # password, and the SSID names the user's home network. Neither belongs
        # in something people paste into public bug reports.
    }
