"""Config flow for the NIBE DVC integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .api import DEFAULT_PORT, NibeDvcError, NibeDvcFan
from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

RECONFIGURE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


async def _async_try_connect(host: str, port: int) -> None:
    """Raise NibeDvcError if the fan does not answer."""
    await NibeDvcFan(host, port).async_update()


class NibeDvcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NIBE DVC."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow started by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                await _async_try_connect(user_input[CONF_HOST], user_input[CONF_PORT])
            except NibeDvcError as err:
                _LOGGER.debug("Cannot connect to %s: %s", user_input[CONF_HOST], err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfigure flow, e.g. after the fan changed IP address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if any(
                other.entry_id != entry.entry_id
                and other.data.get(CONF_HOST) == user_input[CONF_HOST]
                for other in self._async_current_entries()
            ):
                errors["base"] = "already_configured"
            else:
                try:
                    await _async_try_connect(
                        user_input[CONF_HOST], user_input[CONF_PORT]
                    )
                except NibeDvcError as err:
                    _LOGGER.debug(
                        "Cannot connect to %s: %s", user_input[CONF_HOST], err
                    )
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates=user_input
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                RECONFIGURE_DATA_SCHEMA, user_input or dict(entry.data)
            ),
            errors=errors,
        )
