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

from tests.conftest import add_bulk_read

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory

    from custom_components.qube_heatpump.coordinator import QubeCoordinator
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
        add_bulk_read(client)
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
        add_bulk_read(client)
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
        add_bulk_read(client)
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


def test_needs_monotonic_clamping_workinghours() -> None:
    """Test _needs_monotonic_clamping detects workinghours entities."""
    from custom_components.qube_heatpump.coordinator import _needs_monotonic_clamping
    from custom_components.qube_heatpump.hub import EntityDef

    # Test workinghours vendor_id
    ent2 = EntityDef(
        platform="sensor",
        name="Working Hours",
        address=101,
        vendor_id="workinghours_comp",
    )
    assert _needs_monotonic_clamping(ent2) is True

    # Test total_increasing state_class
    ent3 = EntityDef(
        platform="sensor",
        name="Energy",
        address=102,
        state_class="total_increasing",
    )
    assert _needs_monotonic_clamping(ent3) is True

    # Test non-clamped entity
    ent4 = EntityDef(platform="sensor", name="Temperature", address=103)
    assert _needs_monotonic_clamping(ent4) is False


def test_needs_monotonic_clamping_edge_cases() -> None:
    """Test _needs_monotonic_clamping handles edge cases."""
    from custom_components.qube_heatpump.coordinator import _needs_monotonic_clamping
    from custom_components.qube_heatpump.hub import EntityDef

    # Test None name and vendor_id
    ent = EntityDef(platform="sensor", name=None, address=100, vendor_id=None)
    assert _needs_monotonic_clamping(ent) is False


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
        add_bulk_read(client)
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
        add_bulk_read(client)
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


async def test_monotonic_cache_persisted_to_disk(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that the monotonic cache is saved to disk and restored on restart.

    Reproduces GitHub issue #27: after HA restart the monotonic cache is
    empty, so float32 jitter (e.g. 7353.69 → 7353.68) passes through
    unclamped, causing HA to flag "state is not strictly increasing".
    """
    from custom_components.qube_heatpump.coordinator import QubeCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # Verify the coordinator has a Store
    coordinator: QubeCoordinator = entry.runtime_data.coordinator
    assert coordinator._store is not None

    # The monotonic cache in the client should have been populated during first refresh
    client = entry.runtime_data.hub.client
    monotonic_cache = client.monotonic_cache

    # Find a total_increasing entity key in the cache
    total_keys = [k for k in monotonic_cache if monotonic_cache[k] is not None]
    assert len(total_keys) > 0, "Expected at least one total_increasing value in cache"

    # Force a save by calling async_save directly (instead of waiting for delay)
    await coordinator._store.async_save(dict(monotonic_cache))

    # Verify the stored data can be loaded back
    stored = await coordinator._store.async_load()
    assert stored is not None
    assert isinstance(stored, dict)
    assert len(stored) > 0

    # Verify the stored values match the current cache
    for key in total_keys:
        assert key in stored
        assert stored[key] == monotonic_cache[key]


async def test_monotonic_cache_load_seeds_empty_cache(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test async_load_monotonic_cache seeds empty cache from stored data."""
    from custom_components.qube_heatpump.coordinator import QubeCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    coordinator: QubeCoordinator = entry.runtime_data.coordinator

    client = entry.runtime_data.hub.client

    # Write fake data to the store (simulating a previous session)
    fake_cache = {"energy_total_thermic": 7353.69, "workinghours_comp": 12345.0}
    await coordinator._store.async_save(fake_cache)

    # Clear the in-memory cache to simulate restart
    client.monotonic_cache = {}

    # Load should restore the cached values into the client
    await coordinator.async_load_monotonic_cache()

    assert client.monotonic_cache["energy_total_thermic"] == 7353.69
    assert client.monotonic_cache["workinghours_comp"] == 12345.0


async def test_monotonic_cache_load_skips_populated_cache(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test async_load_monotonic_cache does nothing if cache already has data."""
    from custom_components.qube_heatpump.coordinator import QubeCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: QubeCoordinator = entry.runtime_data.coordinator

    client = entry.runtime_data.hub.client

    # Store different data on disk
    await coordinator._store.async_save({"energy_total_thermic": 9999.0})

    # The client's cache should already have values from the first refresh
    original_values = dict(client.monotonic_cache)

    # Load should skip since cache is already populated
    await coordinator.async_load_monotonic_cache()

    # Values should be unchanged (not overwritten by the 9999.0 on disk)
    assert client.monotonic_cache == original_values


async def test_coordinator_tracks_last_update_success_time(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """After a successful refresh, last_update_success_time is populated.

    QubeCoordinator must derive from TimestampDataUpdateCoordinator so the
    shared TariffEnergyTracker dedup guard in sensor.py has a real token to
    compare against instead of a permanent None.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    coordinator: QubeCoordinator = entry.runtime_data.coordinator
    assert coordinator.last_update_success_time is not None


def test_tariff_energy_tracker_dedup_with_real_token() -> None:
    """A tracker fed the same token twice applies the base-total delta once.

    With a real (non-None) token, calling update() a second time with the
    same token but an increased base total must NOT add the delta again -
    the dedup guard should treat the second call as a redundant refresh of
    the same coordinator cycle. With the current always-None token this
    guard never engages, so the delta would be added on every call.
    """
    from datetime import datetime, timezone

    from custom_components.qube_heatpump.const import TARIFF_OPTIONS
    from custom_components.qube_heatpump.sensor import TariffEnergyTracker

    tracker = TariffEnergyTracker(
        base_key="energy_total",
        binary_key="tariff_binary",
        tariffs=list(TARIFF_OPTIONS),
    )

    token = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)

    # binary_key False -> "CH" tariff (see _refresh_current_tariff).
    # First call establishes the baseline total.
    tracker.update({"energy_total": 100.0, "tariff_binary": False}, token)
    assert tracker._totals["CH"] == 0.0

    # Second call, SAME token, but total increased - must be treated as a
    # duplicate notification of the same underlying reading and NOT double
    # count the delta.
    tracker.update({"energy_total": 105.0, "tariff_binary": False}, token)
    assert tracker._totals["CH"] == 0.0, (
        "Delta must not be applied twice for the same dedup token"
    )

    # A genuinely new token should apply the delta exactly once.
    next_token = datetime(2026, 8, 5, 12, 5, 0, tzinfo=timezone.utc)
    tracker.update({"energy_total": 105.0, "tariff_binary": False}, next_token)
    assert tracker._totals["CH"] == 5.0


async def test_tariff_sensor_dedup_end_to_end_via_real_coordinator(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """End-to-end: real coordinator -> sensor callback -> tracker dedup.

    Exercises the actual production wiring instead of a hand-built token:
    the real `sensor.qube_1_electric_consumption_ch_month` entity created by
    the real integration setup (already added to hass via async_add_entities,
    so async_write_ha_state works normally), backed by the real
    QubeCoordinator whose `last_update_success_time` was populated by HA's
    TimestampDataUpdateCoordinator internals - not set manually here. Calling
    the entity's actual `_handle_coordinator_update` does the real
    `getattr(self.coordinator, "last_update_success_time", None)` call.

    Simulates two notifications for the same completed refresh (identical
    token) where the underlying data has ticked up in between - the
    dedup guard must apply the delta only once. Before the coordinator.py
    fix (plain DataUpdateCoordinator, token always None) this test fails
    because the guard's `token is not None` condition never engages and the
    delta is applied on every call.
    """
    from custom_components.qube_heatpump.coordinator import QubeCoordinator
    from custom_components.qube_heatpump.sensor import QubeTariffEnergySensor
    from homeassistant.helpers import entity_platform

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    coordinator: QubeCoordinator = entry.runtime_data.coordinator

    # Mirror sensor.py's own tolerant access (getattr with a None default)
    # rather than a plain attribute read, so this test reproduces the actual
    # doubled-delta symptom on the old base class instead of merely tripping
    # over an AttributeError before reaching the dedup logic.
    def _token() -> object:
        return getattr(coordinator, "last_update_success_time", None)

    # Real refresh already happened during setup, so this is whatever token
    # production wiring actually produces - not fabricated by the test.
    real_token = _token()

    # Find the real, already-added QubeTariffEnergySensor entity (CH monthly
    # electric consumption) via the real entity platform - not a throwaway
    # instance, so async_write_ha_state works without extra scaffolding.
    entity: QubeTariffEnergySensor | None = None
    for platform in entity_platform.async_get_platforms(hass, DOMAIN):
        if platform.domain != "sensor":
            continue
        for candidate in platform.entities.values():
            if getattr(candidate, "_attr_translation_key", None) == (
                "electric_consumption_ch_month"
            ):
                entity = candidate
                break
    assert entity is not None, "electric_consumption_ch_month sensor not found"
    assert isinstance(entity, QubeTariffEnergySensor)

    tracker = entity._tracker
    base_key = tracker.base_key
    baseline = coordinator.data.get(base_key)
    assert isinstance(baseline, (int, float)), (
        f"Expected a numeric baseline for {base_key}, got {baseline!r}"
    )
    totals_before = dict(tracker._totals)

    # No real refresh has happened since setup (no listener has yet called
    # _handle_coordinator_update), so the dedup guard hasn't engaged at all.
    assert tracker._last_token is None

    # First notification for this refresh: base total ticks up +5, applies
    # the delta exactly once.
    coordinator.data[base_key] = baseline + 5.0
    entity._handle_coordinator_update()
    assert _token() == real_token, (
        "No new refresh should have happened between the two notifications"
    )
    assert tracker._totals["CH"] == totals_before["CH"] + 5.0

    # Underlying data ticks up again, but this is a duplicate notification
    # for the SAME completed refresh (same token) - must not double count.
    # On the buggy base class real_token is always None, so the guard's
    # `token is not None` condition never engages and this delta gets
    # applied a second time (totals would read +10 instead of +5).
    coordinator.data[base_key] = baseline + 10.0
    entity._handle_coordinator_update()
    assert tracker._totals["CH"] == totals_before["CH"] + 5.0, (
        "Delta must not be applied twice for the same real coordinator token"
    )

    # Confirms the fix's wiring specifically: production code must be able
    # to obtain a genuinely non-None token from the real coordinator.
    assert real_token is not None


async def test_coordinator_uses_batched_bulk_read(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """The coordinator fetches all values in one bulk call, not per entity."""
    from python_qube_heatpump.entities import BINARY_SENSORS, SENSORS, SWITCHES

    bulk_values: dict = dict.fromkeys(SENSORS, 45.0)
    bulk_values |= dict.fromkeys(BINARY_SENSORS, False)
    bulk_values |= dict.fromkeys(SWITCHES, False)
    mock_qube_client.get_all_entities = AsyncMock(return_value=bulk_values)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert mock_qube_client.get_all_entities.call_count >= 1
    # No per-entity reads during the poll cycle
    assert mock_qube_client.read_entity.call_count == 0

    # Values from the bulk dict must land on entities
    state = hass.states.get("sensor.qube_1_temp_supply")
    assert state is not None
    assert state.state == "45.0"
