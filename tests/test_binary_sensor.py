"""Tests for the Qube Heat Pump binary_sensor platform."""

from typing import Any
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import async_poll, setup_integration

SOURCE_PUMP = "binary_sensor.qube_1_dout_srcpmp_val"
FLOW_ALARM = "binary_sensor.qube_1_alrm_flw"
ALARM_AGGREGATE = "binary_sensor.qube_1_alarm_sensors_active"
ENERGY_STALE = "binary_sensor.qube_1_energy_totals_stale"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every binary sensor entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.BINARY_SENSOR]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("client_values", "expected_state"),
    [
        ({"dout_srcpmp_val": True}, "on"),
        ({"dout_srcpmp_val": False}, "off"),
        ({"dout_srcpmp_val": None}, "unknown"),
    ],
)
async def test_binary_sensor_state_follows_input(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    expected_state: str,
) -> None:
    """The binary sensor mirrors the polled discrete input."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(SOURCE_PUMP)
    assert state.state == expected_state
    assert state.attributes["device_class"] == "running"


async def test_alarm_aggregate_follows_individual_alarms(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The aggregate problem sensor is on while any alarm input is active."""
    client_values["alrm_flw"] = True
    await setup_integration(hass, mock_config_entry)

    flow_alarm = hass.states.get(FLOW_ALARM)
    assert flow_alarm.state == "on"
    assert flow_alarm.attributes["device_class"] == "problem"
    assert hass.states.get(ALARM_AGGREGATE).state == "on"

    client_values["alrm_flw"] = False
    await async_poll(hass, freezer)

    assert hass.states.get(FLOW_ALARM).state == "off"
    assert hass.states.get(ALARM_AGGREGATE).state == "off"


@pytest.mark.parametrize(
    "entity_id",
    [
        "binary_sensor.qube_1_dout_threewayvlv_val",
        "binary_sensor.qube_1_dout_fourwayvlv_val",
    ],
)
async def test_valve_inputs_registered_disabled_and_hidden(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
) -> None:
    """The raw valve inputs stay in the registry but are disabled and hidden.

    The computed valve status sensors are the user-facing entities.
    """
    await setup_integration(hass, mock_config_entry)

    registry_entry = entity_registry.async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry_entry.hidden_by is er.RegistryEntryHider.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_energy_totals_stale_sensor_reflects_coordinator_flag(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The diagnostic problem sensor mirrors coordinator.energy_totals_stale."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(ENERGY_STALE)
    assert state.state == "off"
    assert state.attributes["device_class"] == "problem"
    assert entity_registry.async_get(ENERGY_STALE).entity_category == "diagnostic"

    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.energy_totals_stale = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(ENERGY_STALE).state == "on"
