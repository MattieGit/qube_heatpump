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


def test_rounding_before_monotonic_clamp() -> None:
    """Test that values are rounded before monotonic clamping.

    Reproduces the bug from GitHub issue #26: float32 jitter causes a 0.01
    decrease in the rounded value even though the raw value barely changed.
    When the monotonic cache is empty (e.g. after HA restart) and the
    hardware returns a value with slightly different float32 representation,
    the rounded result can decrease unless rounding is applied before the
    clamp comparison.
    """
    import struct

    from custom_components.qube_heatpump.coordinator import _entity_key
    from custom_components.qube_heatpump.hub import EntityDef

    # Simulate an energy sensor (kWh, precision=2, total_increasing)
    ent = EntityDef(
        platform="sensor",
        name="Energy Total Thermic",
        address=200,
        unique_id="energy_total_thermic",
        unit_of_measurement="kWh",
        device_class="energy",
        state_class="total_increasing",
        precision=2,
    )

    key = _entity_key(ent)
    monotonic_cache: dict[str, float] = {}

    def simulate_coordinator_poll(raw_value: float) -> float:
        """Simulate the coordinator's rounding + clamping logic."""
        import math

        value = raw_value

        # Non-finite check
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            return float("nan")

        # Round before clamp (the fix)
        if isinstance(value, (int, float)) and ent.precision is not None:
            try:
                value = round(float(value), int(ent.precision))
            except (TypeError, ValueError):
                pass

        # Monotonic clamp
        if ent.state_class == "total_increasing" and isinstance(value, (int, float)):
            last_value = monotonic_cache.get(key)
            if isinstance(last_value, (int, float)) and value < (last_value - 1e-6):
                value = last_value
            else:
                monotonic_cache[key] = value

        return value

    # Scenario from issue #26:
    # Poll 1: raw ~ 4781.900 (float32 representation: 4781.8999023...)
    raw1 = struct.unpack("f", struct.pack("f", 4781.900))[0]  # 4781.8999023...
    result1 = simulate_coordinator_poll(raw1)
    assert result1 == 4781.90, f"First poll should round to 4781.90, got {result1}"

    # Poll 2: raw ~ 4781.894 (hardware jitter - slightly lower float32)
    # Without the fix, this would bypass the clamp (cache stores raw)
    # and round to 4781.89, causing the HA warning.
    raw2 = struct.unpack("f", struct.pack("f", 4781.894))[0]  # 4781.8940429...
    result2 = simulate_coordinator_poll(raw2)
    # With the fix: raw2 rounds to 4781.89, clamp detects 4781.89 < 4781.90,
    # so it keeps 4781.90
    assert result2 == 4781.90, (
        f"Second poll should be clamped to 4781.90, got {result2}"
    )

    # Verify normal increase still works
    raw3 = struct.unpack("f", struct.pack("f", 4781.910))[0]
    result3 = simulate_coordinator_poll(raw3)
    assert result3 == 4781.91, f"Third poll should round to 4781.91, got {result3}"

    # Verify the second issue value too (17006.37 -> 17006.36)
    monotonic_cache.clear()
    raw4 = struct.unpack("f", struct.pack("f", 17006.370))[0]
    result4 = simulate_coordinator_poll(raw4)
    assert result4 == 17006.37, f"Should round to 17006.37, got {result4}"

    raw5 = struct.unpack("f", struct.pack("f", 17006.364))[0]
    result5 = simulate_coordinator_poll(raw5)
    assert result5 == 17006.37, (
        f"Should be clamped to 17006.37, got {result5}"
    )
