"""Tests for the Qube Heat Pump sensor platform."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from python_qube_heatpump import StatusCode
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import async_poll, setup_integration

MANIFEST = Path(__file__).parent.parent / "custom_components/qube_heatpump/manifest.json"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Snapshot every sensor entity (the cycle_start attributes depend on now)."""
    freezer.move_to("2026-09-16 12:00:00+00:00")
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_sensor_refresh_updates_value(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A changed register value lands on the entity after the next poll."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get("sensor.qube_1_temp_supply").state == "45.0"

    client_values["temp_supply"] = 50.0
    await async_poll(hass, freezer)

    assert hass.states.get("sensor.qube_1_temp_supply").state == "50.0"


async def test_info_sensor_exposes_hub_metadata(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The diagnostic info sensor is 'ok' and carries firmware/integration versions."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.qube_1_info")
    assert state.state == "ok"
    attrs = state.attributes
    assert attrs["firmware_version"] == "4.10"
    assert attrs["integration_version"] == json.loads(MANIFEST.read_text())["version"]
    assert attrs["label"] == "qube_1"
    assert attrs["host"] == "1.2.3.4"
    assert attrs["ip_address"] == "1.2.3.4"
    assert attrs["errors_connect"] == 0
    assert attrs["errors_read"] == 0


@pytest.mark.parametrize(
    ("alias", "primary", "primary_name"),
    [
        ("flow_rate", "flow", "Measured PVT flow"),
        ("setpoint_room_heat_day", "thermostat_heatsetp_day", "LinQ setpoint heating (day)"),
        ("setpoint_room_heat_night", "thermostat_heatsetp_night", None),
        ("setpoint_room_cool_day", "thermostat_coolsetp_day", None),
        ("setpoint_room_cool_night", "thermostat_coolsetp_night", None),
        ("setpoint_dhw", "tapw_timeprogram_dhwsetp_nolinq", "DHW setpoint (Modbus)"),
    ],
)
async def test_alias_sensors_registered_but_disabled(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    alias: str,
    primary: str,
    primary_name: str | None,
) -> None:
    """Library alias keys stay in the registry but are disabled by default."""
    await setup_integration(hass, mock_config_entry)

    alias_entry = entity_registry.async_get(f"sensor.qube_1_{alias}")
    assert alias_entry is not None
    assert alias_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(f"sensor.qube_1_{alias}") is None

    assert entity_registry.async_get(f"sensor.qube_1_{primary}").disabled_by is None
    primary_state = hass.states.get(f"sensor.qube_1_{primary}")
    assert primary_state is not None
    if primary_name is not None:
        # Description-driven translation_key still yields the translated name
        assert primary_state.attributes["friendly_name"] == f"qube 1 {primary_name}"


@pytest.mark.parametrize("vendor_id", ["temp_room", "cop_calc"])
async def test_rarely_used_sensors_registered_but_disabled(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    vendor_id: str,
) -> None:
    """The LinQ-superseded room temperature and real-time COP start disabled."""
    await setup_integration(hass, mock_config_entry)

    registry_entry = entity_registry.async_get(f"sensor.qube_1_{vendor_id}")
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.parametrize(
    ("entity_id", "client_values", "options", "expected_state"),
    [
        (
            "sensor.qube_1_status_heatpump",
            {"status_code": 16},
            [status.value for status in StatusCode],
            "heating",
        ),
        (
            "sensor.qube_1_status_heatpump",
            {"status_code": 16, "req_antileg_1": True},
            [status.value for status in StatusCode],
            "anti_legionella",
        ),
        (
            "sensor.qube_1_threeway_valve_status",
            {"dout_threewayvlv_val": True},
            ["dhw", "ch"],
            "dhw",
        ),
        (
            "sensor.qube_1_fourway_valve_status",
            {"dout_fourwayvlv_val": False},
            ["heating", "cooling"],
            "cooling",
        ),
    ],
)
async def test_computed_sensors_are_enums(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
    client_values: dict[str, Any],
    options: list[str],
    expected_state: str,
) -> None:
    """Status and valve sensors are ENUM sensors decoded from the raw registers."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(entity_id)
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"] == options
    assert state.state == expected_state
