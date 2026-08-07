"""Tests for NIBE DVC setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nibe_dvc.api import NibeDvcTimeoutError
from custom_components.nibe_dvc.const import DOMAIN

from .conftest import TEST_HOST, TEST_NAME


async def test_setup_entry(hass: HomeAssistant, setup_integration) -> None:
    """The entry loads and exposes its coordinator as runtime data."""
    assert setup_integration.state is ConfigEntryState.LOADED
    assert setup_integration.runtime_data is not None


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """An unreachable fan puts the entry into retry, not a hard failure."""
    mock_fan.async_update.side_effect = NibeDvcTimeoutError("no response")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_multiple_fans(hass: HomeAssistant, mock_fan: AsyncMock) -> None:
    """Several units coexist as independent entries, devices and entities."""
    entries = [
        MockConfigEntry(
            domain=DOMAIN,
            title=title,
            data={CONF_HOST: host, CONF_PORT: 4000, CONF_NAME: title},
        )
        for title, host in (
            ("Basement fan", TEST_HOST),
            ("Living room fan", "192.0.2.6"),
            ("Attic fan", "192.0.2.7"),
        )
    ]
    for entry in entries:
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    for entity_id in (
        "fan.basement_fan",
        "fan.living_room_fan",
        "fan.attic_fan",
    ):
        assert hass.states.get(entity_id) is not None

    # Each entry gets its own device, keyed on the entry id.
    device_reg = dr.async_get(hass)
    device_ids = {
        device_reg.async_get_device({(DOMAIN, entry.entry_id)}).id for entry in entries
    }
    assert len(device_ids) == 3


async def test_unload_one_of_many(hass: HomeAssistant, mock_fan: AsyncMock) -> None:
    """Unloading one unit leaves the others running."""
    first = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={CONF_HOST: TEST_HOST, CONF_PORT: 4000, CONF_NAME: TEST_NAME},
    )
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Living room fan",
        data={CONF_HOST: "192.0.2.6", CONF_PORT: 4000, CONF_NAME: "Living room"},
    )
    for entry in (first, second):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()

    assert first.state is ConfigEntryState.NOT_LOADED
    assert second.state is ConfigEntryState.LOADED
    assert hass.states.get("fan.living_room_fan").state != "unavailable"


async def test_yaml_config_is_rejected(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """The integration is UI only.

    A leftover YAML block is reported to the user and ignored -- it must not
    quietly create a config entry.
    """
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(
        hass, DOMAIN, {DOMAIN: {"devices": [{"ip_address": TEST_HOST}]}}
    )
    await hass.async_block_till_done()

    assert "does not support YAML setup" in caplog.text
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_diagnostics_never_leak_wifi_password(
    hass: HomeAssistant, setup_integration
) -> None:
    """Diagnostics must not carry the Wi-Fi password or the host.

    The unit serves its password in plaintext to anyone on the network, so the
    integration must not be the thing that copies it into a bug report.
    """
    from custom_components.nibe_dvc.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)
    dumped = str(diagnostics)

    assert diagnostics["entry_data"][CONF_HOST] == "**REDACTED**"
    assert TEST_HOST not in dumped
    for key in ("password", "wifi_password", "0x21"):
        assert key not in dumped.lower()


async def test_diagnostics_include_both_frames(
    hass: HomeAssistant, setup_integration
) -> None:
    """Diagnostics carry every raw parameter, from both frames.

    The config frame is the only place the timers, the 0-10 V threshold and the
    cloud flag appear, and none of them has an entity -- diagnostics is the only
    way anyone gets to see them.
    """
    from custom_components.nibe_dvc.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diagnostics["state"]["speed"] == 1
    assert diagnostics["config"]["night_mode_timer"] == 28800
    assert diagnostics["config"]["cloud_activation"] == 1
    assert diagnostics["config"]["sensor_10v_threshold"] == 50


async def test_diagnostics_survive_a_missing_config_frame(
    hass: HomeAssistant, config_entry, mock_fan: AsyncMock
) -> None:
    """Diagnostics must still render for a unit with no config frame."""
    from custom_components.nibe_dvc.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    mock_fan.async_get_config.side_effect = NibeDvcTimeoutError("no config frame")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["config"] is None
    assert diagnostics["state"]["speed"] == 1


async def test_diagnostics_never_leak_the_wifi_network(
    hass: HomeAssistant, setup_integration
) -> None:
    """The SSID names the user's home network, so it stays out of diagnostics.

    Diagnostics are what people paste into public bug reports.
    """
    from custom_components.nibe_dvc.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert "test-wifi" not in str(diagnostics)
