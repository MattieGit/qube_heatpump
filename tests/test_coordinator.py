"""Tests for the Qube Heat Pump coordinator."""

from collections.abc import Callable
from datetime import timedelta
import logging
import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from python_qube_heatpump.entities import BINARY_SENSORS, SENSORS, SWITCHES

from custom_components.qube_heatpump.const import DOMAIN
from custom_components.qube_heatpump.coordinator import (
    CONSECUTIVE_FAILURES_THRESHOLD,
    ENERGY_STALE_TIMEOUT_SECONDS,
    STORAGE_KEY_PREFIX,
    _needs_monotonic_clamping,
    connection_issue_id,
)
from custom_components.qube_heatpump.entity_defs import (
    EntityDef,
    _library_to_ha_entity,
)
from custom_components.qube_heatpump.helpers import entity_data_key
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import async_poll, setup_integration

TEMP_SUPPLY = "sensor.qube_1_temp_supply"
TEMP_RETURN = "sensor.qube_1_temp_return"
ENERGY_TOTAL = "sensor.qube_1_energy_total_electric"
TARIFF_CH_MONTH = "sensor.qube_1_electric_consumption_ch_month"
ENERGY_STALE = "binary_sensor.qube_1_energy_totals_stale"
DEMAND_SWITCH = "switch.qube_1_modbus_demand"

ENERGY_KEY = "energy_total_electric"
THERMIC_KEY = "energy_total_thermic"
POWER_KEY = "power_electric"
VALVE_KEY = "dout_threewayvlv_val"


def _bulk(value: Any = 45.0, coil_value: Any = False) -> dict[str, Any]:
    """Return a full bulk-read result for every library entity."""
    return (
        dict.fromkeys(SENSORS, value)
        | dict.fromkeys(BINARY_SENSORS, coil_value)
        | dict.fromkeys(SWITCHES, coil_value)
    )


def _float32(value: float) -> float:
    """Return ``value`` as the device would report it over Modbus."""
    return struct.unpack("f", struct.pack("f", value))[0]


def _storage_key(entry: MockConfigEntry) -> str:
    """Return the .storage key holding an entry's monotonic baselines."""
    return f"{STORAGE_KEY_PREFIX}_{entry.entry_id}"


def _seed_store(
    hass_storage: dict[str, Any], entry: MockConfigEntry, data: dict[str, float]
) -> None:
    """Pretend a previous session persisted these monotonic baselines."""
    key = _storage_key(entry)
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": data}


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        (_library_to_ha_entity(SENSORS["workinghours_heat_hrsret"]), True),
        (_library_to_ha_entity(SENSORS[ENERGY_KEY]), True),
        (_library_to_ha_entity(SENSORS["temp_supply"]), False),
        (
            EntityDef(
                platform="sensor",
                name="Energy",
                address=102,
                state_class="total_increasing",
            ),
            True,
        ),
        (EntityDef(platform="sensor", name="Temperature", address=103), False),
        (EntityDef(platform="sensor", name=None, address=100, vendor_id=None), False),
    ],
)
def test_needs_monotonic_clamping(entity: EntityDef, expected: bool) -> None:
    """Only total_increasing entities are clamped."""
    assert _needs_monotonic_clamping(entity) is expected


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        (
            EntityDef(
                platform="sensor", name="Test", address=100, unique_id="test_sensor"
            ),
            "test_sensor",
        ),
        (
            EntityDef(
                platform="sensor", name="Test", address=100, input_type="holding"
            ),
            "sensor_holding_100",
        ),
    ],
)
def test_entity_data_key(entity: EntityDef, expected: str) -> None:
    """The coordinator keys values by unique_id, falling back to the address."""
    assert entity_data_key(entity) == expected


async def test_coordinator_connects_before_polling(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A disconnected client is connected during setup before any read."""
    mock_qube_client.is_connected = False

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_qube_client.connect.assert_awaited()
    assert hass.states.get(TEMP_SUPPLY).state == "45.0"


async def test_coordinator_reads_every_value_in_one_bulk_call(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each poll is a single batched read, never one transaction per entity."""
    mock_qube_client.get_all_entities = AsyncMock(return_value=_bulk())

    await setup_integration(hass, mock_config_entry)

    assert mock_qube_client.get_all_entities.await_count == 1
    assert mock_qube_client.read_entity.await_count == 0
    assert hass.states.get(TEMP_SUPPLY).state == "45.0"

    await async_poll(hass, freezer)

    assert mock_qube_client.get_all_entities.await_count == 2
    assert mock_qube_client.read_entity.await_count == 0


async def test_coordinator_does_not_resolve_ip_per_poll(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """DNS resolution only happens once at setup, not on every poll cycle.

    async_resolve_ip only feeds a diagnostic sensor; resolving DNS again
    every poll was redundant per-poll work.
    """
    with patch(
        "custom_components.qube_heatpump.hub.QubeHub.async_resolve_ip",
        new_callable=AsyncMock,
    ) as resolve_ip:
        await setup_integration(hass, mock_config_entry)
        calls_after_setup = resolve_ip.await_count
        assert calls_after_setup == 1

        await async_poll(hass, freezer)

        assert resolve_ip.await_count == calls_after_setup


def _break_connect(client: MagicMock, values: dict[str, Any]) -> Callable[[], None]:
    """Make the device refuse the connection."""
    client.is_connected = False
    client.connect = AsyncMock(return_value=False)

    def _undo() -> None:
        client.connect = AsyncMock(return_value=True)

    return _undo


def _break_read(client: MagicMock, values: dict[str, Any]) -> Callable[[], None]:
    """Make the bulk read raise instead of returning values."""
    original = client.get_all_entities
    client.get_all_entities = AsyncMock(side_effect=OSError("network down"))

    def _undo() -> None:
        client.get_all_entities = original

    return _undo


def _break_device(client: MagicMock, values: dict[str, Any]) -> Callable[[], None]:
    """Make every register read as None, as an unresponsive device does."""
    values.update(dict.fromkeys(SENSORS | BINARY_SENSORS | SWITCHES))

    def _undo() -> None:
        values.clear()

    return _undo


@pytest.mark.parametrize(
    "break_device",
    [_break_connect, _break_read, _break_device],
    ids=["connect_refused", "read_error", "no_data"],
)
async def test_entities_go_unavailable_on_failed_poll_and_recover(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    break_device: Callable[[MagicMock, dict[str, Any]], Callable[[], None]],
) -> None:
    """A failed poll makes every entity unavailable; the next good poll restores it."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert hass.states.get(TEMP_SUPPLY).state == "45.0"

    undo = break_device(mock_qube_client, client_values)
    await async_poll(hass, freezer)

    assert coordinator.last_update_success is False
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(TEMP_SUPPLY).state == STATE_UNAVAILABLE
    assert hass.states.get(DEMAND_SWITCH).state == STATE_UNAVAILABLE

    undo()
    await async_poll(hass, freezer)

    assert coordinator.last_update_success is True
    assert hass.states.get(TEMP_SUPPLY).state == "45.0"
    assert hass.states.get(DEMAND_SWITCH).state == "off"


async def test_partially_missing_bulk_read_keeps_entry_available(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A partially failed block read only marks the missing registers unknown."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator

    client_values.update(dict.fromkeys(SENSORS | BINARY_SENSORS | SWITCHES))
    client_values["temp_supply"] = 33.0
    await async_poll(hass, freezer)

    assert coordinator.last_update_success is True
    assert hass.states.get(TEMP_SUPPLY).state == "33.0"
    assert hass.states.get(TEMP_RETURN).state == STATE_UNKNOWN


async def test_non_finite_values_warn_once_per_register(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each non-finite register warns once and then logs at DEBUG; state is unknown."""
    nonfinite_keys = ["temp_supply", "temp_return", "temp_dhw"]
    for key in nonfinite_keys:
        client_values[key] = float("nan")

    with caplog.at_level(logging.DEBUG, logger="custom_components.qube_heatpump"):
        await setup_integration(hass, mock_config_entry)
        first = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING
            and "Non-finite value" in record.message
        ]
        assert len(first) == len(nonfinite_keys)

        caplog.clear()
        await async_poll(hass, freezer)

    assert not [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "Non-finite value" in record.message
    ]
    repeats = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG and "Non-finite value" in record.message
    ]
    assert len(repeats) == len(nonfinite_keys)
    for key in nonfinite_keys:
        assert hass.states.get(f"sensor.qube_1_{key}").state == STATE_UNKNOWN


async def test_total_increasing_value_is_rounded_before_it_is_clamped(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Float32 jitter must not produce a rounded decrease (issue #26).

    The raw readings differ by 0.006 kWh, but both round to a two-decimal
    value; clamping on the rounded value keeps the sensor from going
    backwards, which Home Assistant would flag as a broken total.
    """
    client_values[ENERGY_KEY] = _float32(4781.900)
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENERGY_TOTAL).state == "4781.9"

    client_values[ENERGY_KEY] = _float32(4781.894)
    await async_poll(hass, freezer)
    assert hass.states.get(ENERGY_TOTAL).state == "4781.9"

    # A genuine increase still passes through
    client_values[ENERGY_KEY] = _float32(4781.910)
    await async_poll(hass, freezer)
    assert hass.states.get(ENERGY_TOTAL).state == "4781.91"


async def test_monotonic_baseline_restored_from_disk(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
) -> None:
    """A baseline stored before restart clamps the very first reading (issue #27).

    Without it the in-memory cache starts empty, so float32 jitter right
    after a restart passes through as a decrease.
    """
    _seed_store(hass_storage, mock_config_entry, {ENERGY_KEY: 7353.69})
    client_values[ENERGY_KEY] = 7353.68

    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENERGY_TOTAL).state == "7353.69"


async def test_monotonic_cache_load_keeps_live_values(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A populated cache is never overwritten by what happens to be on disk."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    live = dict(mock_qube_client.monotonic_cache)
    assert live, "the first poll should have seeded the cache"

    _seed_store(hass_storage, mock_config_entry, {ENERGY_KEY: 9999.0})
    await coordinator.async_load_monotonic_cache()

    assert mock_qube_client.monotonic_cache == live


async def test_monotonic_cache_flushed_to_disk_on_unload(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A pending delayed save is written immediately when the entry unloads."""
    await setup_integration(hass, mock_config_entry)
    expected = dict(mock_qube_client.monotonic_cache)
    assert expected
    assert _storage_key(mock_config_entry) not in hass_storage

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass_storage[_storage_key(mock_config_entry)]["data"] == expected


async def test_clear_monotonic_cache_accepts_a_lower_reading(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a deliberate counter reset the stored baseline must be forgotten."""
    _seed_store(hass_storage, mock_config_entry, {ENERGY_KEY: 1000.0})
    client_values[ENERGY_KEY] = 12.0
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENERGY_TOTAL).state == "1000.0"

    await mock_config_entry.runtime_data.coordinator.async_clear_monotonic_cache()
    await async_poll(hass, freezer)

    mock_qube_client.clear_monotonic_cache.assert_called_once()
    assert _storage_key(mock_config_entry) not in hass_storage
    assert hass.states.get(ENERGY_TOTAL).state == "12.0"


async def test_tariff_sensor_applies_a_delta_once_per_refresh(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
) -> None:
    """Two notifications for the same refresh must not double count the delta.

    The tariff tracker deduplicates on ``last_update_success_time``, which
    only exists because QubeCoordinator derives from
    TimestampDataUpdateCoordinator. On a plain DataUpdateCoordinator the
    token is always None, the guard never engages and the delta lands twice.
    """
    client_values[ENERGY_KEY] = 100.0
    client_values[VALVE_KEY] = False  # three-way valve on CH
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert coordinator.last_update_success_time is not None

    start = float(hass.states.get(TARIFF_CH_MONTH).state)

    coordinator.data[ENERGY_KEY] = 105.0
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert float(hass.states.get(TARIFF_CH_MONTH).state) == start + 5.0

    # Same refresh token, higher total: a redundant notification
    coordinator.data[ENERGY_KEY] = 110.0
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert float(hass.states.get(TARIFF_CH_MONTH).state) == start + 5.0


async def test_energy_totals_flagged_stale_while_power_is_drawn(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Totals frozen for 15 minutes under load raise the diagnostic flag once."""
    client_values.update({ENERGY_KEY: 1000.0, THERMIC_KEY: 4000.0, POWER_KEY: 1200.0})
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENERGY_STALE).state == "off"

    with caplog.at_level(logging.WARNING):
        freezer.tick(timedelta(seconds=ENERGY_STALE_TIMEOUT_SECONDS + 60))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        assert hass.states.get(ENERGY_STALE).state == "on"
        await async_poll(hass, freezer)

    assert caplog.text.count("have not advanced") == 1

    client_values[THERMIC_KEY] = 4000.3
    await async_poll(hass, freezer)

    assert hass.states.get(ENERGY_STALE).state == "off"


async def test_energy_staleness_is_gated_on_the_power_reading(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Frozen totals are normal while idle, and unknown power leaves the timer be.

    The tracker takes an explicit ``now`` so these boundaries can be driven
    directly; there is no public surface that sets the monotonic clock.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator._energy_last_values.clear()
    coordinator._energy_stale_since = None
    coordinator.energy_totals_stale = False

    idle = {ENERGY_KEY: 1000.0, THERMIC_KEY: 4000.0, POWER_KEY: 55.0}
    for moment in (0.0, ENERGY_STALE_TIMEOUT_SECONDS * 2):
        coordinator._track_energy_staleness(idle, now=moment)
    assert coordinator.energy_totals_stale is False
    assert coordinator._energy_stale_since is None

    # Load starts: the timer only counts from here
    loaded = {**idle, POWER_KEY: 900.0}
    coordinator._track_energy_staleness(loaded, now=10_000.0)
    assert coordinator._energy_stale_since == 10_000.0
    assert coordinator.energy_totals_stale is False

    # A missing power reading is neither evidence for nor against staleness
    coordinator._track_energy_staleness(
        {**loaded, POWER_KEY: None}, now=10_000.0 + ENERGY_STALE_TIMEOUT_SECONDS / 2
    )
    assert coordinator._energy_stale_since == 10_000.0
    assert coordinator.energy_totals_stale is False

    coordinator._track_energy_staleness(
        loaded, now=10_000.0 + ENERGY_STALE_TIMEOUT_SECONDS
    )
    assert coordinator.energy_totals_stale is True


async def test_repair_issue_raised_on_the_fifth_failure_and_cleared_on_recovery(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Five consecutive failed polls raise a non-fixable repair issue."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    issue_id = connection_issue_id(mock_config_entry.entry_id)
    registry = ir.async_get(hass)

    undo = _break_connect(mock_qube_client, {})
    for _ in range(CONSECUTIVE_FAILURES_THRESHOLD - 1):
        await coordinator.async_refresh()
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    await coordinator.async_refresh()

    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.translation_key == "connection_failed"
    assert issue.translation_placeholders == {"host": "1.2.3.4"}

    undo()
    await coordinator.async_refresh()

    assert registry.async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.parametrize("action", ["reload", "remove"])
async def test_repair_issue_cleared_by_entry_lifecycle(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    action: str,
) -> None:
    """An issue from a previous coordinator survives neither a reload nor removal."""
    await setup_integration(hass, mock_config_entry)
    entry_id = mock_config_entry.entry_id
    issue_id = connection_issue_id(entry_id)
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="connection_failed",
        translation_placeholders={"host": "1.2.3.4"},
    )
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    if action == "reload":
        await hass.config_entries.async_reload(entry_id)
    else:
        await hass.config_entries.async_remove(entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_clamp_holding_a_dipped_counter_is_not_stale(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A small backward step keeps HA at the old maximum, but the raw register
    is still advancing: that is the clamp doing its job, not a stalled device.
    """
    from custom_components.qube_heatpump.coordinator import (
        ENERGY_STALE_TIMEOUT_SECONDS,
    )

    client_values.update(
        {
            "energy_total_electric": 1000.0,
            "energy_total_thermic": 4000.0,
            "power_electric": 1500.0,
        }
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    # The controller steps back by 0.19 kWh and then climbs slowly
    client_values["energy_total_thermic"] = 3999.81
    client_values["energy_total_electric"] = 999.9
    for _ in range(7):
        client_values["energy_total_thermic"] += 0.02
        client_values["energy_total_electric"] += 0.01
        freezer.tick(timedelta(seconds=ENERGY_STALE_TIMEOUT_SECONDS / 4))
        await async_poll(hass, freezer)

    # HA still shows the held maximums...
    assert hass.states.get("sensor.qube_1_energy_total_thermic").state == "4000.0"
    assert coordinator.raw_data["energy_total_thermic"] < 4000.0
    # ...but nothing is stale, because the raw registers keep moving
    assert coordinator.energy_totals_stale is False
    assert hass.states.get(ENERGY_STALE).state == "off"


async def test_frozen_raw_counters_are_stale_even_if_clamped_value_is_stable(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Raw registers frozen under load -> stale, and raw_data shows it."""
    from custom_components.qube_heatpump.coordinator import (
        ENERGY_STALE_TIMEOUT_SECONDS,
    )

    client_values.update(
        {
            "energy_total_electric": 1000.0,
            "energy_total_thermic": 4000.0,
            "power_electric": 1500.0,
        }
    )
    await setup_integration(hass, mock_config_entry)
    for _ in range(5):
        freezer.tick(timedelta(seconds=ENERGY_STALE_TIMEOUT_SECONDS / 4))
        await async_poll(hass, freezer)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert coordinator.energy_totals_stale is True
    assert coordinator.raw_data["energy_total_electric"] == 1000.0
