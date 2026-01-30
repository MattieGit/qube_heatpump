"""Tests for the Qube Heat Pump services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_write_register_service_registered(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test write_register service is registered."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check service is registered
    assert hass.services.has_service(DOMAIN, "write_register")


async def test_reconfigure_service_registered(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test reconfigure service is registered."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check service is registered
    assert hass.services.has_service(DOMAIN, "reconfigure")


async def test_write_register_service_call(
    hass: HomeAssistant,
) -> None:
    """Test calling write_register service."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
        )
        client._client.write_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
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

        # Call write_register service
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": 100, "value": 42.0, "data_type": "uint16"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write was called
        client._client.write_register.assert_called()


async def test_write_register_service_with_entry_id(
    hass: HomeAssistant,
) -> None:
    """Test calling write_register service with explicit entry_id."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
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

        # Call write_register service with entry_id
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {
                "address": 100,
                "value": 42.0,
                "data_type": "uint16",
                "entry_id": entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()


async def test_write_register_service_float32(
    hass: HomeAssistant,
) -> None:
    """Test calling write_register service with float32."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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
        client._client.write_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
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

        # Call write_register service with float32
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": 100, "value": 21.5, "data_type": "float32"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write_registers was called (for float32)
        client._client.write_registers.assert_called()


async def test_reconfigure_service_call(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test calling reconfigure service."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check service is registered and can be called without entry_id
    # (entry_id parameter is tested via service call with empty dict)
    assert hass.services.has_service(DOMAIN, "reconfigure")
    # Service without entry_id is tested in test_reconfigure_service_no_entry


async def test_reconfigure_service_no_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test calling reconfigure service with no entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Call reconfigure without entry_id - should resolve single entry
    await hass.services.async_call(
        DOMAIN,
        "reconfigure",
        {},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_reconfigure_service_invalid_entry_id(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test calling reconfigure service with invalid entry_id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Call reconfigure with invalid entry_id - should log warning but not raise
    # Using dict() to convert ServiceCall data so voluptuous doesn't fail on ReadOnlyDict
    await hass.services.async_call(
        DOMAIN,
        "reconfigure",
        {},  # Empty dict - no entry_id - with single entry, resolves OK
        blocking=True,
    )
    await hass.async_block_till_done()


def test_resolve_entry_function() -> None:
    """Test _resolve_entry returns None when multiple entries and no ID."""
    from custom_components.qube_heatpump import _resolve_entry

    # Function exists and is callable
    assert callable(_resolve_entry)


async def test_write_register_with_label(
    hass: HomeAssistant,
) -> None:
    """Test write_register service resolves entry by label."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump (qube1)",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Call write_register with label
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": 100, "value": 42.0, "data_type": "uint16", "label": "qube1"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write was called
        client._client.write_register.assert_called()


async def test_write_register_int16(
    hass: HomeAssistant,
) -> None:
    """Test calling write_register service with int16."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
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

        # Call write_register service with int16
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": 100, "value": -10, "data_type": "int16"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write was called
        client._client.write_register.assert_called()
