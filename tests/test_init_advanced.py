"""Advanced tests for Qube Heat Pump integration initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_wp_qube_title_rename(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test that entries with WP Qube title are renamed to Qube Heat Pump."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="WP Qube (my_label)",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.title == "Qube Heat Pump (my_label)"


async def test_service_reconfigure_no_entry_id_multiple_entries(
    hass: HomeAssistant,
) -> None:
    """Test reconfigure service warns when multiple entries and no entry_id."""
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

        # Create two entries
        entry1 = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube 1",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry1.add_to_hass(hass)
        await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

        entry2 = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.5"},
            title="Qube 2",
            unique_id=f"{DOMAIN}-1.2.3.5-502",
        )
        entry2.add_to_hass(hass)
        await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

        # Call reconfigure without entry_id - should log warning
        with patch("custom_components.qube_heatpump._LOGGER.warning") as mock_warning:
            await hass.services.async_call(
                DOMAIN,
                "reconfigure",
                {},
                blocking=True,
            )
            await hass.async_block_till_done()

            # Should have logged a warning about no entry resolved
            assert mock_warning.called


async def test_service_reconfigure_flow_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test reconfigure service handles flow errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Mock flow to raise HomeAssistantError
    with (
        patch.object(
            hass.config_entries.flow,
            "async_init",
            side_effect=HomeAssistantError("Flow error"),
        ),
        patch("custom_components.qube_heatpump._LOGGER.warning") as mock_warning,
    ):
        await hass.services.async_call(
            DOMAIN,
            "reconfigure",
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Should have logged warning about flow not available
        mock_warning.assert_called()


async def test_service_reconfigure_unexpected_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test reconfigure service handles unexpected errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Mock flow to raise unexpected error
    with (
        patch.object(
            hass.config_entries.flow,
            "async_init",
            side_effect=RuntimeError("Unexpected"),
        ),
        patch("custom_components.qube_heatpump._LOGGER.warning") as mock_warning,
    ):
        await hass.services.async_call(
            DOMAIN,
            "reconfigure",
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Should have logged warning about unexpected error
        mock_warning.assert_called()


async def test_write_register_no_runtime_data(
    hass: HomeAssistant,
) -> None:
    """Test write_register handles entry without runtime_data."""
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

        # Temporarily clear runtime_data to test error path
        original_data = entry.runtime_data
        entry.runtime_data = None

        with patch("custom_components.qube_heatpump._LOGGER.error") as mock_error:
            await hass.services.async_call(
                DOMAIN,
                "write_register",
                {"address": 100, "value": 42.0, "data_type": "uint16"},
                blocking=True,
            )
            await hass.async_block_till_done()

            # Restore for cleanup
            entry.runtime_data = original_data

            # Should have logged error about not loaded
            mock_error.assert_called()


async def test_write_register_no_hub(
    hass: HomeAssistant,
) -> None:
    """Test write_register handles missing hub."""
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

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Set hub to None
        original_hub = entry.runtime_data.hub
        entry.runtime_data.hub = None

        with patch("custom_components.qube_heatpump._LOGGER.error") as mock_error:
            await hass.services.async_call(
                DOMAIN,
                "write_register",
                {"address": 100, "value": 42.0, "data_type": "uint16"},
                blocking=True,
            )
            await hass.async_block_till_done()

            # Restore for cleanup
            entry.runtime_data.hub = original_hub

            # Should have logged error about no hub
            mock_error.assert_called()


async def test_write_register_write_fails(
    hass: HomeAssistant,
) -> None:
    """Test write_register handles write failure for non-existent address."""
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

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Write to non-existent address should raise HomeAssistantError
        # (hub now requires a matching writable entity)
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "write_register",
                {"address": 100, "value": 42.0, "data_type": "uint16"},
                blocking=True,
            )


async def test_resolve_entry_by_runtime_label(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test _resolve_entry finds entry by runtime_data.label."""
    from custom_components.qube_heatpump import _resolve_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump (custom_label)",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Should find by label
    result = _resolve_entry(hass, None, "custom_label")
    assert result is not None
    assert result.entry_id == entry.entry_id


async def test_resolve_entry_not_loaded(
    hass: HomeAssistant,
) -> None:
    """Test _resolve_entry handles entries without runtime_data."""
    from custom_components.qube_heatpump import _resolve_entry

    # Add entry but don't set it up (no runtime_data)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    # Should return None since entry isn't loaded
    result = _resolve_entry(hass, None, "some_label")
    assert result is None


async def test_options_update_listener(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test that options update listener reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Update options - should trigger reload
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock_reload:
        hass.config_entries.async_update_entry(entry, options={"test_option": "value"})
        await hass.async_block_till_done()

        # Reload should have been called
        mock_reload.assert_called_once_with(entry.entry_id)


async def test_entity_creation_failure_skipped(
    hass: HomeAssistant,
) -> None:
    """Test that entity creation failures are skipped gracefully."""
    from homeassistant.helpers import entity_registry as er

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

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        # Mock entity registry to raise on first few calls
        ent_reg = er.async_get(hass)
        original_async_get_or_create = ent_reg.async_get_or_create
        call_count = [0]

        def mock_get_or_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("Test error")
            return original_async_get_or_create(*args, **kwargs)

        with patch.object(
            ent_reg,
            "async_get_or_create",
            side_effect=mock_get_or_create,
        ):
            # Should still complete setup despite entity creation failure
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            assert entry.state is ConfigEntryState.LOADED


async def test_integration_version_fallback(
    hass: HomeAssistant,
) -> None:
    """Test integration version uses fallback when not loaded."""
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

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        # Mock async_get_loaded_integration to return None
        with (
            patch(
                "custom_components.qube_heatpump.async_get_loaded_integration",
                return_value=None,
            ),
            patch(
                "custom_components.qube_heatpump.async_get_integration",
                return_value=MagicMock(version="2.0.0"),
            ),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            assert entry.state is ConfigEntryState.LOADED
            assert entry.runtime_data.version == "2.0.0"
