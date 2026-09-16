"""Tests for the Qube Heat Pump diagnostics."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant

from . import setup_integration


async def test_diagnostics(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The whole dump is snapshotted: entry, hub, entities and last values."""
    await setup_integration(hass, mock_config_entry)

    assert await async_get_config_entry_diagnostics(hass, mock_config_entry) == snapshot


async def test_diagnostics_redacts_only_network_identifiers(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Host, port and resolved IP are hidden; register keys stay readable.

    The register keys are the library's names for the modbus registers, so
    a dump can be matched against the register documentation.
    """
    await setup_integration(hass, mock_config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["hub"]["host"] == "**REDACTED**"
    assert diagnostics["hub"]["port"] == "**REDACTED**"
    assert diagnostics["hub"]["resolved_ip"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["host"] == "**REDACTED**"

    hub = mock_config_entry.runtime_data.hub
    assert [entity["unique_id"] for entity in diagnostics["entities"]] == [
        ent.unique_id for ent in hub.entities
    ]
    assert (
        diagnostics["coordinator_data"]
        == mock_config_entry.runtime_data.coordinator.data
    )
    assert "temp_supply" in diagnostics["coordinator_data"]


async def test_diagnostics_reports_error_counters(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The counters that make an issue report actionable track the hub."""
    await setup_integration(hass, mock_config_entry)
    hub = mock_config_entry.runtime_data.hub
    hub.inc_read_error()
    hub.inc_read_error()

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["hub"]["err_read"] == 2
    assert diagnostics["hub"]["err_connect"] == 0
    assert diagnostics["firmware_version"] == mock_config_entry.runtime_data.version
