from __future__ import annotations

from unittest.mock import AsyncMock
import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump import async_unload_entry
from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN, PLATFORMS


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
