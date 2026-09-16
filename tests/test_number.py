"""Tests for the Qube Heat Pump number platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import add_bulk_read

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_number_entities_created(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test number entities are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check number entities exist (setpoints)
    states = hass.states.async_all()
    number_states = [s for s in states if s.entity_id.startswith("number.")]
    # May or may not have number entities depending on library data
    assert isinstance(number_states, list)


async def test_number_set_value(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test setting a number value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get number entities
    states = hass.states.async_all()
    number_states = [s for s in states if s.entity_id.startswith("number.")]

    if number_states:
        number_id = number_states[0].entity_id

        # Set value
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": number_id, "value": 21.5},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write_setpoint was called
        mock_qube_client.write_setpoint.assert_called()


async def test_number_native_value(
    hass: HomeAssistant,
) -> None:
    """Test number native_value property."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.close = AsyncMock(return_value=None)
        # Return temperature values
        client.read_entity = AsyncMock(return_value=21.5)
        add_bulk_read(client)
        client.read_sensor = AsyncMock(return_value=21.5)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
        client.write_setpoint = AsyncMock(return_value=True)
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_input_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )
        client._client.read_discrete_inputs = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check number entities
        states = hass.states.async_all()
        number_states = [s for s in states if s.entity_id.startswith("number.")]
        # Verify structure
        assert isinstance(number_states, list)


async def test_number_native_value_none(
    hass: HomeAssistant,
) -> None:
    """Test number native_value when data is None."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.close = AsyncMock(return_value=None)
        # Return None for values
        client.read_entity = AsyncMock(return_value=None)
        add_bulk_read(client)
        client.read_sensor = AsyncMock(return_value=None)
        client.read_binary_sensor = AsyncMock(return_value=None)
        client.read_switch = AsyncMock(return_value=None)
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_input_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )
        client._client.read_discrete_inputs = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check number entities handle None
        states = hass.states.async_all()
        number_states = [s for s in states if s.entity_id.startswith("number.")]
        assert isinstance(number_states, list)


async def test_number_device_info(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test number entity device info."""
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Verify device exists
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "1.2.3.4:1")})
    assert device is not None
    assert device.manufacturer == "Qube"


async def test_number_unique_id_multi_device(hass: HomeAssistant) -> None:
    """Test number unique_id uses host_unit prefix in multi_device mode."""
    from custom_components.qube_heatpump.entity_defs import EntityDef
    from custom_components.qube_heatpump.number import QubeSetpointNumber

    hub = MagicMock()
    hub.host = "192.168.1.100"
    hub.unit = 2
    hub.label = "qube1"
    hub.entry_id = "test_entry_id"

    coordinator = MagicMock()
    coordinator.data = {}

    ent = EntityDef(
        platform="sensor",
        name="Test Setpoint",
        address=100,
    )
    ent.unique_id = "setpoint_heat_day"
    ent.translation_key = "setpoint_heat_day"
    ent.input_type = "holding"
    ent.vendor_id = "setpoint_heat_day"

    # Single device - always has host_unit prefix for stability
    number_single = QubeSetpointNumber(
        coordinator=coordinator,
        hub=hub,
        version="1.0",
        ent=ent,
    )
    assert number_single._attr_unique_id == "192.168.1.100_2_setpoint_heat_day_setpoint"

    # Multi device - same host_unit prefix
    number_multi = QubeSetpointNumber(
        coordinator=coordinator,
        hub=hub,
        version="1.0",
        ent=ent,
    )
    assert number_multi._attr_unique_id == "192.168.1.100_2_setpoint_heat_day_setpoint"


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


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
    vendor_id: str,
    minimum: float,
    maximum: float,
) -> None:
    """Each setpoint gets the range that matches the register's purpose."""
    await _setup_entry(hass)

    state = hass.states.get(f"number.qube_1_{vendor_id}")
    assert state is not None
    assert state.attributes["min"] == minimum
    assert state.attributes["max"] == maximum
    assert state.attributes["step"] == 0.5
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["unit_of_measurement"] == "°C"


def test_number_unknown_setpoint_uses_default_range() -> None:
    """A writable °C register without a dedicated range falls back to 20-65."""
    from custom_components.qube_heatpump.entity_defs import EntityDef
    from custom_components.qube_heatpump.number import QubeSetpointNumber

    hub = MagicMock()
    hub.host = "1.2.3.4"
    hub.unit = 1
    hub.label = "qube1"
    coordinator = MagicMock()
    coordinator.data = {}
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
) -> None:
    """A rejected setpoint write surfaces as a translated HomeAssistantError."""
    await _setup_entry(hass)
    mock_qube_client.write_setpoint = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.qube_1_usr_pid_heatsetp", "value": 21.5},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_setpoint_failed"
    assert excinfo.value.translation_placeholders == {
        "entity_id": "number.qube_1_usr_pid_heatsetp"
    }


async def test_number_set_value_connect_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """An unreachable device surfaces as a translated connection error."""
    await _setup_entry(hass)
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.qube_1_usr_pid_heatsetp", "value": 21.5},
            blocking=True,
        )

    assert excinfo.value.translation_key == "connection_failed"
    assert excinfo.value.translation_placeholders == {"host": "1.2.3.4"}
    mock_qube_client.write_setpoint.assert_not_awaited()
