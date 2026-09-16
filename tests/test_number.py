"""Tests for the Qube Heat Pump number platform."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.const import DOMAIN
from custom_components.qube_heatpump.entity_defs import EntityDef
from custom_components.qube_heatpump.number import QubeSetpointNumber
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import setup_integration

HEAT_SETPOINT = "number.qube_1_usr_pid_heatsetp"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every number entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.NUMBER]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("client_values", "expected_state"),
    [
        ({"usr_pid_heatsetp": 21.5}, "21.5"),
        ({"usr_pid_heatsetp": None}, "unknown"),
    ],
)
async def test_number_native_value(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    expected_state: str,
) -> None:
    """The number mirrors the register value; an unreadable register is unknown."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(HEAT_SETPOINT).state == expected_state


async def test_number_set_value(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Setting a value writes the register by library key and re-polls."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(HEAT_SETPOINT).state == "45.0"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": HEAT_SETPOINT, "value": 21.5},
        blocking=True,
    )

    mock_qube_client.write_setpoint.assert_awaited_once_with("usr_pid_heatsetp", 21.5)
    assert hass.states.get(HEAT_SETPOINT).state == "21.5"


@pytest.mark.parametrize(
    ("vendor_id", "minimum", "maximum"),
    [
        ("tapw_timeprogram_dhwsetp_nolinq", 40.0, 65.0),
        ("usr_pid_heatsetp", 20.0, 65.0),
        ("usr_pid_coolsetp", 7.0, 25.0),
    ],
)
async def test_number_setpoint_ranges(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    vendor_id: str,
    minimum: float,
    maximum: float,
) -> None:
    """Each setpoint gets the range that matches the register's purpose."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(f"number.qube_1_{vendor_id}")
    assert state is not None
    assert state.attributes["min"] == minimum
    assert state.attributes["max"] == maximum
    assert state.attributes["step"] == 0.5
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["unit_of_measurement"] == "°C"


def test_number_unknown_setpoint_uses_default_range() -> None:
    """A writable °C register without a dedicated range falls back to 20-65."""
    hub = MagicMock(host="1.2.3.4", unit=1, label="qube1")
    coordinator = MagicMock(data={})
    ent = EntityDef(
        platform="sensor",
        name="Other setpoint",
        address=200,
        vendor_id="some_other_setpoint",
        unique_id="some_other_setpoint",
        translation_key="some_other_setpoint",
        unit_of_measurement="°C",
        writable=True,
    )

    number = QubeSetpointNumber(coordinator, hub, "1.0", ent)

    assert number.native_min_value == 20.0
    assert number.native_max_value == 65.0


async def test_number_set_value_write_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected setpoint write surfaces as a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.write_setpoint = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": HEAT_SETPOINT, "value": 21.5},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_setpoint_failed"
    assert excinfo.value.translation_placeholders == {"entity_id": HEAT_SETPOINT}


async def test_number_set_value_connect_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unreachable device surfaces as a translated connection error."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": HEAT_SETPOINT, "value": 21.5},
            blocking=True,
        )

    assert excinfo.value.translation_key == "connection_failed"
    assert excinfo.value.translation_placeholders == {"host": "1.2.3.4"}
    mock_qube_client.write_setpoint.assert_not_awaited()
