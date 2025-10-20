from __future__ import annotations

from unittest.mock import AsyncMock
import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump import async_unload_entry
from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_SHOW_LABEL_IN_NAME,
    DOMAIN,
    PLATFORMS,
)


@pytest.mark.asyncio
async def test_async_setup_entry_registers_integration(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the config entry setup populates hass.data and forwards platforms."""

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.1"})
    entry.add_to_hass(hass)

    forward_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward_mock)

    first_refresh_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "custom_components.qube_heatpump.DataUpdateCoordinator.async_config_entry_first_refresh",
        first_refresh_mock,
    )

    monkeypatch.setattr(
        "homeassistant.setup.async_setup_component",
        AsyncMock(return_value=True),
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]
    stored = hass.data[DOMAIN][entry.entry_id]
    assert stored["label"] == "qube1"
    manifest = json.loads((Path("custom_components/qube_heatpump/manifest.json")).read_text())
    assert stored["version"] == manifest.get("version")

    forward_mock.assert_called_once_with(entry, PLATFORMS)
    first_refresh_mock.assert_called_once()
    assert hass.services.has_service(DOMAIN, "reconfigure")


@pytest.mark.asyncio
async def test_async_setup_entry_includes_room_temp_sensor(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the LINQ room temperature sensor definition is registered."""

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "203.0.113.10"})
    entry.add_to_hass(hass)

    forward_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward_mock)

    first_refresh_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "custom_components.qube_heatpump.DataUpdateCoordinator.async_config_entry_first_refresh",
        first_refresh_mock,
    )

    monkeypatch.setattr(
        "homeassistant.setup.async_setup_component",
        AsyncMock(return_value=True),
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hub = hass.data[DOMAIN][entry.entry_id]["hub"]
    sensor_unique_ids = {ent.unique_id for ent in hub.entities if ent.platform == "sensor"}
    assert "modbus_roomtemp" in sensor_unique_ids


@pytest.mark.asyncio
async def test_multi_device_enforces_label_suffix(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure applying the second hub forces label suffixing for both entries."""

    entry_one = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10"})
    entry_two = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.11"})
    forward_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward_mock)

    first_refresh_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "custom_components.qube_heatpump.DataUpdateCoordinator.async_config_entry_first_refresh",
        first_refresh_mock,
    )

    unload_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload_mock)

    monkeypatch.setattr(
        "homeassistant.setup.async_setup_component",
        AsyncMock(return_value=True),
    )

    entry_one.add_to_hass(hass)
    await hass.config_entries.async_setup(entry_one.entry_id)
    await hass.async_block_till_done()

    stored_first = hass.data[DOMAIN][entry_one.entry_id]
    assert stored_first["apply_label_in_name"] is False

    entry_two.add_to_hass(hass)
    await hass.config_entries.async_setup(entry_two.entry_id)
    await hass.async_block_till_done()

    stored_second = hass.data[DOMAIN][entry_two.entry_id]
    assert stored_second["apply_label_in_name"] is True

    stored_first = hass.data[DOMAIN][entry_one.entry_id]
    assert stored_first["apply_label_in_name"] is True
    assert entry_one.options[CONF_SHOW_LABEL_IN_NAME] is True
    assert entry_two.options[CONF_SHOW_LABEL_IN_NAME] is True


@pytest.mark.asyncio
async def test_async_unload_entry_cleans_up(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure unload removes stored data and closes the hub."""

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "198.51.100.2"})
    entry.add_to_hass(hass)

    unload_platforms = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload_platforms)

    class DummyHub:
        async def async_close(self) -> None:  # pragma: no cover - replaced by mock
            return None

    hub = DummyHub()
    hub.async_close = AsyncMock()  # type: ignore[assignment]

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
    }

    result = await async_unload_entry(hass, entry)

    assert result is True
    unload_platforms.assert_called_once_with(entry, PLATFORMS)
    hub.async_close.assert_awaited()
    assert hass.data.get(DOMAIN, {}).get(entry.entry_id) is None
