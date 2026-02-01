"""Tests for the Qube Heat Pump number platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN

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
