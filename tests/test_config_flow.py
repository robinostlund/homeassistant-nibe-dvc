"""Tests for the NIBE DVC config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.nibe_dvc.api import NibeDvcTimeoutError
from custom_components.nibe_dvc.const import DOMAIN

from .conftest import TEST_HOST, TEST_NAME, TEST_PORT


async def test_user_flow(hass: HomeAssistant, mock_fan: AsyncMock) -> None:
    """A user can add a fan through the UI."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: TEST_HOST, CONF_PORT: TEST_PORT, CONF_NAME: TEST_NAME},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_NAME
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
        CONF_PORT: TEST_PORT,
        CONF_NAME: TEST_NAME,
    }


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_fan: AsyncMock
) -> None:
    """An unreachable fan shows an error and lets the user retry."""
    mock_fan.async_update.side_effect = NibeDvcTimeoutError("no response")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: TEST_HOST, CONF_PORT: TEST_PORT, CONF_NAME: TEST_NAME},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Recovering within the same flow succeeds.
    mock_fan.async_update.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: TEST_HOST, CONF_PORT: TEST_PORT, CONF_NAME: TEST_NAME},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """The same host cannot be added twice."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: TEST_HOST, CONF_PORT: TEST_PORT, CONF_NAME: TEST_NAME},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"




async def test_reconfigure(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """The host can be changed without losing the entity."""
    result = await setup_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.0.2.6", CONF_PORT: TEST_PORT}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert setup_integration.data[CONF_HOST] == "192.0.2.6"
    # The name is preserved rather than reset.
    assert setup_integration.data[CONF_NAME] == TEST_NAME


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, setup_integration, mock_fan: AsyncMock
) -> None:
    """A bad new address is rejected and the old one is kept."""
    result = await setup_integration.start_reconfigure_flow(hass)
    mock_fan.async_update.side_effect = NibeDvcTimeoutError("no response")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.0.2.99", CONF_PORT: TEST_PORT}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert setup_integration.data[CONF_HOST] == TEST_HOST
