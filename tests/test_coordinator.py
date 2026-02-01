"""Tests for the Qube Heat Pump coordinator."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory

    from homeassistant.core import HomeAssistant


async def test_coordinator_fetches_data(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test coordinator fetches data from hub."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert config entry state
    assert entry.state is ConfigEntryState.LOADED

    # Assert entity state via core state machine - data was fetched
    states = hass.states.async_all()
    sensor_states = [s for s in states if s.entity_id.startswith("sensor.")]
    assert len(sensor_states) > 0
    # At least one sensor should have a valid (non-unavailable) state
    valid_states = [s for s in sensor_states if s.state != STATE_UNAVAILABLE]
    assert len(valid_states) > 0


async def test_coordinator_reconnects_when_disconnected(
    hass: HomeAssistant,
) -> None:
    """Test coordinator reconnects when client is disconnected."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False  # Start disconnected
        client.connect = AsyncMock(return_value=True)
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
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert config entry state
        assert entry.state is ConfigEntryState.LOADED

        # Connection should have been attempted since is_connected was False
        client.connect.assert_called()


async def test_coordinator_handles_fetch_error(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator handles fetch errors gracefully."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)
        # First call succeeds for setup
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
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert initial state is loaded
        assert entry.state is ConfigEntryState.LOADED

        # Make next fetch fail
        client.read_entity.side_effect = Exception("Communication error")
        client.read_sensor.side_effect = Exception("Communication error")

        # Trigger coordinator refresh via time advancement
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        # Entry should still be loaded (coordinator handles errors gracefully)
        assert entry.state is ConfigEntryState.LOADED


async def test_coordinator_handles_no_data(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator handles no data response gracefully."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)
        # First call succeeds for setup
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
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert initial state is loaded
        assert entry.state is ConfigEntryState.LOADED

        # Make next fetch return None
        client.read_entity.return_value = None
        client.read_sensor.return_value = None

        # Trigger coordinator refresh via time advancement
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        # Entry should still be loaded
        assert entry.state is ConfigEntryState.LOADED


def test_is_working_hours_entity_bedrijfsuren() -> None:
    """Test _is_working_hours_entity detects bedrijfsuren entities."""
    from custom_components.qube_heatpump.coordinator import _is_working_hours_entity
    from custom_components.qube_heatpump.hub import EntityDef

    # Test bedrijfsuren name
    ent = EntityDef(platform="sensor", name="Bedrijfsuren compressor", address=100)
    assert _is_working_hours_entity(ent) is True

    # Test workinghours vendor_id
    ent2 = EntityDef(
        platform="sensor",
        name="Working Hours",
        address=101,
        vendor_id="workinghours_comp",
    )
    assert _is_working_hours_entity(ent2) is True

    # Test non-working hours entity
    ent3 = EntityDef(platform="sensor", name="Temperature", address=102)
    assert _is_working_hours_entity(ent3) is False


def test_is_working_hours_entity_edge_cases() -> None:
    """Test _is_working_hours_entity handles edge cases."""
    from custom_components.qube_heatpump.coordinator import _is_working_hours_entity
    from custom_components.qube_heatpump.hub import EntityDef

    # Test None name and vendor_id
    ent = EntityDef(platform="sensor", name=None, address=100, vendor_id=None)
    assert _is_working_hours_entity(ent) is False


def test_entity_key_generation() -> None:
    """Test _entity_key generates correct keys."""
    from custom_components.qube_heatpump.coordinator import _entity_key
    from custom_components.qube_heatpump.hub import EntityDef

    # Test with unique_id
    ent = EntityDef(
        platform="sensor", name="Test", address=100, unique_id="test_sensor"
    )
    assert _entity_key(ent) == "test_sensor"

    # Test without unique_id (fallback to address-based key)
    ent2 = EntityDef(platform="sensor", name="Test", address=100, input_type="holding")
    assert _entity_key(ent2) == "sensor_holding_100"


async def test_coordinator_non_finite_value(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator handles non-finite values (NaN, inf)."""
    import math

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)
        # First call returns valid data for setup
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
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # Make next fetch return NaN
        client.read_entity.return_value = float("nan")
        client.read_sensor.return_value = float("nan")

        # Trigger coordinator refresh
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        # Entry should still be loaded (NaN handled as unavailable)
        assert entry.state is ConfigEntryState.LOADED


async def test_coordinator_monotonicity_violation(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator handles monotonicity violations for total_increasing sensors."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)
        # First call returns high value
        client.read_entity = AsyncMock(return_value=1000.0)
        client.read_sensor = AsyncMock(return_value=1000.0)
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
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # Make next fetch return a lower value (monotonicity violation)
        client.read_entity.return_value = 500.0
        client.read_sensor.return_value = 500.0

        # Trigger coordinator refresh
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        # Entry should still be loaded
        assert entry.state is ConfigEntryState.LOADED
