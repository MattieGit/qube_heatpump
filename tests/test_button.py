"""Tests for the Qube Heat Pump button platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

RELOAD_BUTTON = "button.qube_1_reload"
CLEAR_CACHE_BUTTON = "button.qube_1_clear_monotonic_cache"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every button entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.BUTTON]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_reload_button_reloads_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Pressing the reload button reloads this config entry."""
    await setup_integration(hass, mock_config_entry)

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload:
        await hass.services.async_call(
            "button", "press", {"entity_id": RELOAD_BUTTON}, blocking=True
        )

    reload.assert_awaited_once_with(mock_config_entry.entry_id)


async def test_clear_monotonic_cache_button_press(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Pressing the clear-cache button delegates to the coordinator."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator

    with patch.object(
        coordinator, "async_clear_monotonic_cache", new=AsyncMock()
    ) as clear:
        await hass.services.async_call(
            "button", "press", {"entity_id": CLEAR_CACHE_BUTTON}, blocking=True
        )

    clear.assert_awaited_once()
