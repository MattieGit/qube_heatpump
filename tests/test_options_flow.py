"""Tests for the Qube Heat Pump options flow."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_DHW_SCHEDULE_ENABLED,
    CONF_DHW_SETPOINT,
    CONF_DHW_USE_CONTROLLER_SETPOINT,
    CONF_NAME,
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DOMAIN,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr

from . import setup_integration

RESOLVE_HOST = "custom_components.qube_heatpump.config_flow.async_resolve_host"
OPEN_CONNECTION = "custom_components.qube_heatpump.config_flow.asyncio.open_connection"

CLIMATE_ENTITY_ID = "climate.qube_1_thermostat"
ROOM_SENSOR = "sensor.living_room_temperature"


def _tcp_ok() -> Any:
    """Patch the TCP probe so no test opens a real socket."""
    writer = MagicMock(wait_closed=AsyncMock())
    return patch(OPEN_CONNECTION, return_value=(AsyncMock(), writer))


async def _start_options_flow(
    hass: HomeAssistant, entry: MockConfigEntry
) -> dict[str, Any]:
    """Open the options flow and return the first form."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    return result


async def test_options_flow_renames_the_device(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A new name is written to the entry data and title, and reloads the entry."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.data[CONF_NAME] == "qube 1"

    result = await _start_options_flow(hass, mock_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: mock_config_entry.data[CONF_HOST],
            CONF_NAME: "my heat pump",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.data[CONF_NAME] == "my heat pump"
    assert mock_config_entry.title == "my heat pump"


@pytest.mark.parametrize(
    ("host", "resolves_to", "connects", "expected_error"),
    [
        ("", None, True, "invalid_host"),
        ("qube-new.local", "192.0.2.20", True, "duplicate_ip"),
        ("192.0.2.99", None, False, "cannot_connect"),
    ],
    ids=["empty", "duplicate_ip", "cannot_connect"],
)
async def test_options_flow_rejects_a_bad_host(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    host: str,
    resolves_to: str | None,
    connects: bool,
    expected_error: str,
) -> None:
    """A host that is empty, taken or unreachable is a form error, not a change."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.20", CONF_NAME: "qube 2"},
        unique_id=f"{DOMAIN}-192.0.2.20-502",
        title="qube 2",
    ).add_to_hass(hass)
    await setup_integration(hass, mock_config_entry)

    result = await _start_options_flow(hass, mock_config_entry)
    tcp = (
        _tcp_ok()
        if connects
        else patch(OPEN_CONNECTION, side_effect=OSError("Connection refused"))
    )
    resolve = (
        patch(RESOLVE_HOST, return_value=resolves_to)
        if resolves_to
        else patch(RESOLVE_HOST, side_effect=lambda value: value or None)
    )
    with tcp, resolve:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: host, CONF_NAME: "qube 1"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: expected_error}
    assert mock_config_entry.data[CONF_HOST] == "1.2.3.4"


async def test_options_flow_host_change_keeps_the_device(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Moving the device to a new host updates the entry but keeps its device."""
    await setup_integration(hass, mock_config_entry)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, mock_config_entry.entry_id), mock_config_entry.entry_id
    )
    assert device is not None

    result = await _start_options_flow(hass, mock_config_entry)
    with _tcp_ok():
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.0.2.99", CONF_NAME: "qube 1"},
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.data[CONF_HOST] == "192.0.2.99"
    assert mock_config_entry.unique_id == f"{DOMAIN}-192.0.2.99-502"
    devices = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert [d.id for d in devices] == [device.id]
    assert devices[0].identifiers == {(DOMAIN, mock_config_entry.entry_id)}


async def test_options_flow_thermostat_step_creates_the_thermostat(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Enabling the thermostat asks for a sensor, stores it and reloads the entry."""
    hass.states.async_set(ROOM_SENSOR, "20.0", {"device_class": "temperature"})
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(CLIMATE_ENTITY_ID) is None

    result = await _start_options_flow(hass, mock_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: mock_config_entry.data[CONF_HOST],
            CONF_NAME: "qube 1",
            CONF_THERMOSTAT_ENABLED: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "thermostat"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_THERMOSTAT_SENSOR: ROOM_SENSOR},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_THERMOSTAT_ENABLED] is True
    assert mock_config_entry.options[CONF_THERMOSTAT_SENSOR] == ROOM_SENSOR
    # The reload is what makes the option take effect
    assert hass.states.get(CLIMATE_ENTITY_ID) is not None


@pytest.mark.parametrize(
    "config_entry_options",
    [{CONF_THERMOSTAT_ENABLED: True, CONF_THERMOSTAT_SENSOR: ROOM_SENSOR}],
)
async def test_options_flow_thermostat_step_defaults_to_the_current_sensor(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reopening the step offers the configured sensor rather than an empty box."""
    hass.states.async_set(ROOM_SENSOR, "20.0", {"device_class": "temperature"})
    await setup_integration(hass, mock_config_entry)

    result = await _start_options_flow(hass, mock_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: mock_config_entry.data[CONF_HOST],
            CONF_NAME: "qube 1",
            CONF_THERMOSTAT_ENABLED: True,
        },
    )

    assert result["step_id"] == "thermostat"
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_THERMOSTAT_SENSOR] == ROOM_SENSOR


async def test_options_flow_dhw_step_stores_controller_setpoint_toggle(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The DHW step offers the controller-setpoint toggle (default on) and stores it."""
    await setup_integration(hass, mock_config_entry)

    result = await _start_options_flow(hass, mock_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: mock_config_entry.data[CONF_HOST],
            CONF_NAME: "qube 1",
            CONF_DHW_SCHEDULE_ENABLED: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dhw_schedule"

    # The toggle defaults to on (the controller's own setpoint is left alone)
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_DHW_USE_CONTROLLER_SETPOINT] is True

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DHW_USE_CONTROLLER_SETPOINT: False,
            CONF_DHW_SETPOINT: 52.0,
            "dhw_start_time": "13:00",
            "dhw_end_time": "15:00",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_DHW_USE_CONTROLLER_SETPOINT] is False
    assert mock_config_entry.options[CONF_DHW_SETPOINT] == 52.0


@pytest.mark.parametrize(
    "config_entry_options",
    [
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_SETPOINT: 52.0,
            "dhw_start_time": "13:00",
            "dhw_end_time": "15:00",
            "unit_id": 1,
        }
    ],
)
async def test_options_flow_disabling_feature_drops_its_settings(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Turning the DHW schedule off removes its sub-settings and reloads once."""
    await setup_integration(hass, mock_config_entry)

    result = await _start_options_flow(hass, mock_config_entry)
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock_reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: mock_config_entry.data[CONF_HOST],
                CONF_NAME: "qube 1",
                CONF_DHW_SCHEDULE_ENABLED: False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {
        CONF_DHW_SCHEDULE_ENABLED: False,
        CONF_THERMOSTAT_ENABLED: False,
        "unit_id": 1,  # legacy value is left alone
    }
    mock_reload.assert_awaited_once_with(mock_config_entry.entry_id)
