"""Tests for the Qube Heat Pump water heater platform."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.const import DOMAIN
from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
)
from homeassistant.const import ATTR_TEMPERATURE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import setup_integration

WATER_HEATER = "water_heater.qube_1_dhw"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot the water heater entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.WATER_HEATER]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("client_values", "expected_state", "temperature", "target"),
    [
        (
            {"temp_dhw": 48.2, "tapw_timeprogram_dhwsetp_nolinq": 50.0},
            STATE_HEAT_PUMP,
            48.2,
            50.0,
        ),
        ({"tapw_timeprogram_bms_forced": True}, STATE_PERFORMANCE, 45.0, 45.0),
        (
            {
                "temp_dhw": None,
                "tapw_timeprogram_dhwsetp_nolinq": None,
                "tapw_timeprogram_bms_forced": None,
            },
            "unknown",
            None,
            None,
        ),
    ],
)
async def test_water_heater_state(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    expected_state: str,
    temperature: float | None,
    target: float | None,
) -> None:
    """The entity mirrors the DHW temperature, setpoint and forced coil."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(WATER_HEATER)
    assert state.state == expected_state
    assert state.attributes["current_temperature"] == temperature
    assert state.attributes["temperature"] == target


async def test_set_temperature(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Setting the temperature writes the DHW setpoint register and re-polls."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        "water_heater",
        SERVICE_SET_TEMPERATURE,
        {"entity_id": WATER_HEATER, ATTR_TEMPERATURE: 52.5},
        blocking=True,
    )

    mock_qube_client.write_setpoint.assert_awaited_once_with(
        "tapw_timeprogram_dhwsetp_nolinq", 52.5
    )
    assert hass.states.get(WATER_HEATER).attributes["temperature"] == 52.5


@pytest.mark.parametrize(
    ("client_values", "mode", "coil"),
    [
        ({"tapw_timeprogram_bms_forced": False}, STATE_PERFORMANCE, True),
        ({"tapw_timeprogram_bms_forced": True}, STATE_HEAT_PUMP, False),
    ],
)
async def test_set_operation_mode(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    mode: str,
    coil: bool,
) -> None:
    """Performance starts the forced DHW run; heat pump stops it."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        "water_heater",
        SERVICE_SET_OPERATION_MODE,
        {"entity_id": WATER_HEATER, ATTR_OPERATION_MODE: mode},
        blocking=True,
    )

    mock_qube_client.write_switch.assert_awaited_once_with(
        "tapw_timeprogram_bms_forced", coil
    )
    assert hass.states.get(WATER_HEATER).state == mode


async def test_set_temperature_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected setpoint write surfaces as a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.write_setpoint = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_TEMPERATURE,
            {"entity_id": WATER_HEATER, ATTR_TEMPERATURE: 52.5},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_setpoint_failed"
    assert excinfo.value.translation_placeholders == {"entity_id": WATER_HEATER}


async def test_set_operation_mode_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected coil write surfaces as a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.write_switch = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_OPERATION_MODE,
            {"entity_id": WATER_HEATER, ATTR_OPERATION_MODE: STATE_PERFORMANCE},
            blocking=True,
        )

    assert excinfo.value.translation_key == "write_switch_failed"
    assert hass.states.get(WATER_HEATER).state == STATE_HEAT_PUMP


async def test_connect_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unreachable device surfaces as a translated connection error."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(side_effect=OSError("down"))

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_TEMPERATURE,
            {"entity_id": WATER_HEATER, ATTR_TEMPERATURE: 52.5},
            blocking=True,
        )

    assert excinfo.value.translation_key == "connection_failed"
    mock_qube_client.write_setpoint.assert_not_awaited()
