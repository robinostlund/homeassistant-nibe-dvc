"""DataUpdateCoordinator for the NIBE DVC integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NibeDvcConfig,
    NibeDvcError,
    NibeDvcFan,
    NibeDvcNetwork,
    NibeDvcState,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from . import NibeDvcConfigEntry

_LOGGER = logging.getLogger(__name__)


class NibeDvcDataUpdateCoordinator(DataUpdateCoordinator[NibeDvcState]):
    """Poll a single ventilation unit and fan out its state to entities."""

    config_entry: NibeDvcConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: NibeDvcConfigEntry,
        fan: NibeDvcFan,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {fan.host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.fan = fan
        self.network: NibeDvcNetwork | None = None
        self.config: NibeDvcConfig | None = None

    async def _async_setup(self) -> None:
        """Read the network settings once, before the first refresh.

        These effectively never change while the entry is loaded, so there is no
        point spending a round trip on them every poll -- a reload picks up a
        change. Failure is not fatal; the unit simply gets no Wi-Fi sensor.
        """
        try:
            self.network = await self.fan.async_get_network()
        except NibeDvcError as err:
            _LOGGER.debug("Could not read network settings from %s: %s", self.fan.host, err)

    async def _async_update_data(self) -> NibeDvcState:
        """Fetch the current state and settings from the fan."""
        try:
            state = await self.fan.async_update()
            # The boost threshold and run-on delay live in the config frame,
            # not the status frame, so both are needed every poll.
            self.config = await self.fan.async_get_config()
        except NibeDvcError as err:
            raise UpdateFailed(f"Error communicating with {self.fan.host}: {err}") from err
        return state

    async def async_execute_config(
        self, action: Callable[[], Awaitable[NibeDvcConfig]]
    ) -> None:
        """Run a config write and publish the settings it returns.

        Config writes are applied silently by the unit, so the api re-reads the
        config frame and hands back the confirmed values.
        """
        try:
            self.config = await action()
        except NibeDvcError as err:
            raise HomeAssistantError(
                f"Error communicating with {self.fan.host}: {err}"
            ) from err
        self.async_update_listeners()

    async def async_execute(
        self, action: Callable[[], Awaitable[NibeDvcState]]
    ) -> None:
        """Run a write command and publish the state it returns.

        Every command is answered with a full status frame, so entities get the
        confirmed device state immediately instead of waiting for the next poll
        or guessing optimistically.
        """
        try:
            state = await action()
        except NibeDvcError as err:
            raise HomeAssistantError(
                f"Error communicating with {self.fan.host}: {err}"
            ) from err
        self.async_set_updated_data(state)
