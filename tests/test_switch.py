"""Tests for the Qube Heat Pump switch platform."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import async_poll, setup_integration

DEMAND_SWITCH = "switch.qube_1_modbus_demand"
FORCED_DHW_SWITCH = "switch.qube_1_tapw_timeprogram_bms_forced"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every switch entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.SWITCH]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("client_values", "expected_state"),
    [
        ({"modbus_demand": True}, "on"),
        ({"modbus_demand": False}, "off"),
        ({"modbus_demand": None}, "unknown"),
    ],
)
async def test_switch_state_follows_coil(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    expected_state: str,
) -> None:
    """The switch state mirrors the polled coil value."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(DEMAND_SWITCH).state == expected_state


@pytest.mark.parametrize(
    ("initial", "service", "written", "expected_state"),
    [
        (False, "turn_on", True, "on"),
        (True, "turn_off", False, "off"),
    ],
)
async def test_switch_turn_on_off(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    initial: bool,
    service: str,
    written: bool,
    expected_state: str,
) -> None:
    """Turning the switch writes the coil by library key and re-polls."""
    client_values["modbus_demand"] = initial
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        "switch", service, {"entity_id": DEMAND_SWITCH}, blocking=True
    )

    mock_qube_client.write_switch.assert_awaited_once_with("modbus_demand", written)
    assert hass.states.get(DEMAND_SWITCH).state == expected_state


@pytest.mark.parametrize("client_values", [{"tapw_timeprogram_bms_forced": True}])
async def test_forced_dhw_switch_reports_pending_request_when_coil_stays_on(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Turn-off acknowledged but coil still on -> real state on + pending_request."""
    # The controller acknowledges the write but keeps the coil on
    mock_qube_client.write_switch = AsyncMock(return_value=True)
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FORCED_DHW_SWITCH)
    assert state.state == "on"
    assert state.attributes["pending_request"] is False

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": FORCED_DHW_SWITCH}, blocking=True
    )

    mock_qube_client.write_switch.assert_awaited_with("tapw_timeprogram_bms_forced", False)
    state = hass.states.get(FORCED_DHW_SWITCH)
    assert state.state == "on", "must surface the coil's real state, not the optimistic one"
    assert state.attributes["pending_request"] is True

    # The controller clears the coil itself once the DHW run completes
    client_values["tapw_timeprogram_bms_forced"] = False
    await async_poll(hass, freezer)
    state = hass.states.get(FORCED_DHW_SWITCH)
    assert state.state == "off"
    assert state.attributes["pending_request"] is False


@pytest.mark.parametrize("client_values", [{"tapw_timeprogram_bms_forced": True}])
async def test_forced_dhw_switch_turn_on_clears_pending_request(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Turning the switch back on cancels a pending turn-off."""
    mock_qube_client.write_switch = AsyncMock(return_value=True)
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": FORCED_DHW_SWITCH}, blocking=True
    )
    assert hass.states.get(FORCED_DHW_SWITCH).attributes["pending_request"] is True

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": FORCED_DHW_SWITCH}, blocking=True
    )
    assert hass.states.get(FORCED_DHW_SWITCH).attributes["pending_request"] is False


async def test_other_switches_have_no_pending_attribute(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Only the forced-DHW coil exposes pending_request."""
    await setup_integration(hass, mock_config_entry)

    assert "pending_request" not in hass.states.get(DEMAND_SWITCH).attributes


async def test_switch_write_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected coil write surfaces as a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.write_switch = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": DEMAND_SWITCH}, blocking=True
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_switch_failed"
    assert excinfo.value.translation_placeholders == {"entity_id": DEMAND_SWITCH}
    assert hass.states.get(DEMAND_SWITCH).state == "off"


@pytest.mark.parametrize("client_values", [{"modbus_demand": True}])
async def test_switch_connect_failure_raises_translated_error(
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
            "switch", "turn_off", {"entity_id": DEMAND_SWITCH}, blocking=True
        )

    assert excinfo.value.translation_key == "connection_failed"
    mock_qube_client.write_switch.assert_not_awaited()
