"""Tests for the DHW schedule state holder and its diagnostic entities."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_DHW_END_TIME,
    CONF_DHW_SCHEDULE_ENABLED,
    CONF_DHW_SETPOINT,
    CONF_DHW_START_TIME,
    CONF_DHW_USE_CONTROLLER_SETPOINT,
    CONF_HOST,
    DOMAIN,
)
from custom_components.qube_heatpump.dhw_scheduler import (
    DhwScheduleState,
    next_occurrence,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

AMS = ZoneInfo("Europe/Amsterdam")
BINARY_ID = "binary_sensor.qube_1_dhw_schedule"
NEXT_START_ID = "sensor.qube_1_dhw_schedule_next_start"


# --- pure state holder -------------------------------------------------------


def test_next_occurrence_same_day_and_across_midnight() -> None:
    """Before the configured time -> today; at/after it -> tomorrow."""
    now = datetime(2026, 9, 16, 12, 0, tzinfo=AMS)
    assert next_occurrence(now, 13, 0) == datetime(2026, 9, 16, 13, 0, tzinfo=AMS)

    now = datetime(2026, 9, 16, 14, 30, tzinfo=AMS)
    assert next_occurrence(now, 13, 0) == datetime(2026, 9, 17, 13, 0, tzinfo=AMS)

    # Exactly at the configured minute counts as passed (the callback has fired)
    now = datetime(2026, 9, 16, 13, 0, tzinfo=AMS)
    assert next_occurrence(now, 13, 0) == datetime(2026, 9, 17, 13, 0, tzinfo=AMS)


def test_next_occurrence_keeps_wall_clock_across_dst() -> None:
    """The next start stays at 13:00 local time when DST starts overnight."""
    # 2026-03-29 is the spring-forward day in Europe/Amsterdam
    now = datetime(2026, 3, 28, 14, 0, tzinfo=AMS)
    nxt = next_occurrence(now, 13, 0)
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.minute) == (2026, 3, 29, 13, 0)
    assert now.utcoffset().total_seconds() == 3600
    assert nxt.utcoffset().total_seconds() == 7200
    # 23 real hours, not 24
    assert (nxt - now).total_seconds() == 23 * 3600


def test_state_from_options_disabled_is_empty() -> None:
    """A disabled schedule renders a consistent off state."""
    state = DhwScheduleState.from_options({})
    assert state.enabled is False
    assert state.next_start is None
    assert state.next_end is None
    assert state.window_active is False
    assert state.setpoint_source is None


def test_state_from_options_enabled_controller_setpoint() -> None:
    """Enabled with the default (controller) setpoint source."""
    now = datetime(2026, 9, 16, 14, 0, tzinfo=AMS)
    state = DhwScheduleState.from_options(
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "13:00",
            CONF_DHW_END_TIME: "15:00",
            CONF_DHW_SETPOINT: 55.0,  # stored but not used
        },
        now=now,
    )
    assert state.enabled is True
    assert state.start_time == "13:00"
    assert state.end_time == "15:00"
    assert state.setpoint_source == "controller"
    assert state.fixed_setpoint is None
    assert state.window_active is True  # 14:00 lies in 13:00-15:00
    assert state.next_start == datetime(2026, 9, 17, 13, 0, tzinfo=AMS)
    assert state.next_end == datetime(2026, 9, 16, 15, 0, tzinfo=AMS)


def test_state_from_options_fixed_setpoint_and_overnight_window() -> None:
    """Fixed setpoint source and a window that crosses midnight."""
    now = datetime(2026, 9, 16, 23, 30, tzinfo=AMS)
    state = DhwScheduleState.from_options(
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "22:00",
            CONF_DHW_END_TIME: "06:00",
            CONF_DHW_USE_CONTROLLER_SETPOINT: False,
            CONF_DHW_SETPOINT: 52.5,
        },
        now=now,
    )
    assert state.setpoint_source == "fixed"
    assert state.fixed_setpoint == 52.5
    assert state.window_active is True
    assert state.next_end == datetime(2026, 9, 17, 6, 0, tzinfo=AMS)
    assert state.next_start == datetime(2026, 9, 17, 22, 0, tzinfo=AMS)


def test_record_start_end_toggle_window_and_advance_next() -> None:
    """Callbacks flip window_active, stamp last_*, and roll next_* forward."""
    state = DhwScheduleState.from_options(
        {CONF_DHW_SCHEDULE_ENABLED: True, CONF_DHW_START_TIME: "13:00", CONF_DHW_END_TIME: "15:00"},
        now=datetime(2026, 9, 16, 8, 0, tzinfo=AMS),
    )
    assert state.window_active is False

    fired = datetime(2026, 9, 16, 13, 0, tzinfo=AMS)
    state.record_start(fired)
    assert state.window_active is True
    assert state.last_start == fired
    assert state.next_start == datetime(2026, 9, 17, 13, 0, tzinfo=AMS)
    assert state.next_end == datetime(2026, 9, 16, 15, 0, tzinfo=AMS)

    ended = datetime(2026, 9, 16, 15, 0, tzinfo=AMS)
    state.record_end(ended)
    assert state.window_active is False
    assert state.last_end == ended
    assert state.next_end == datetime(2026, 9, 17, 15, 0, tzinfo=AMS)


def test_listeners_are_notified_and_can_unsubscribe() -> None:
    """Entities subscribe to state changes and unsubscribe on removal."""
    state = DhwScheduleState()
    calls: list[int] = []
    unsub = state.async_add_listener(lambda: calls.append(1))
    state.async_update_listeners()
    assert calls == [1]
    unsub()
    state.async_update_listeners()
    assert calls == [1]


# --- entities ------------------------------------------------------------------


async def _setup(hass: HomeAssistant, options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options=options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_render_off_and_unknown_when_disabled(
    hass: HomeAssistant, mock_qube_client: MagicMock, caplog
) -> None:
    """Disabled schedule: binary sensor off, timestamp unknown, INFO line logged."""
    entry = await _setup(hass, {})
    assert entry.runtime_data.dhw_schedule is not None
    assert entry.runtime_data.dhw_schedule.enabled is False

    binary = hass.states.get(BINARY_ID)
    assert binary is not None
    assert binary.state == "off"
    assert binary.attributes["window_active"] is False
    assert "start" not in binary.attributes
    assert binary.attributes["icon"] == "mdi:calendar-clock"

    ts = hass.states.get(NEXT_START_ID)
    assert ts is not None
    assert ts.state == "unknown"
    assert ts.attributes["device_class"] == "timestamp"
    assert "DHW schedule disabled" in caplog.text


async def test_entities_render_enabled_schedule(
    hass: HomeAssistant, mock_qube_client: MagicMock, caplog
) -> None:
    """Enabled schedule: attributes, next start timestamp and INFO line."""
    with patch(
        "custom_components.qube_heatpump.dhw_scheduler.async_track_time_change",
        return_value=MagicMock(),
    ):
        await _setup(
            hass,
            {
                CONF_DHW_SCHEDULE_ENABLED: True,
                CONF_DHW_START_TIME: "13:00",
                CONF_DHW_END_TIME: "15:00",
                CONF_DHW_USE_CONTROLLER_SETPOINT: False,
                CONF_DHW_SETPOINT: 52.0,
            },
        )

    binary = hass.states.get(BINARY_ID)
    assert binary.state == "on"
    assert binary.attributes["start"] == "13:00"
    assert binary.attributes["end"] == "15:00"
    assert binary.attributes["setpoint_source"] == "fixed"
    assert binary.attributes["fixed_setpoint"] == 52.0
    assert binary.attributes["last_start"] is None
    assert binary.attributes["last_end"] is None

    ts = hass.states.get(NEXT_START_ID)
    assert ts.state != "unknown"
    parsed = datetime.fromisoformat(ts.state)
    assert parsed.tzinfo is not None
    assert "DHW schedule enabled 13:00-15:00, setpoint source: fixed 52.0" in caplog.text


async def test_scheduler_callbacks_update_entities_immediately(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Firing start/end updates window_active, last_*, icon and next start without a poll."""
    calls: list[dict] = []

    def _fake_track(hass_, action, *, hour=None, minute=None, second=None):
        calls.append({"action": action, "hour": hour})
        return MagicMock()

    with patch(
        "custom_components.qube_heatpump.dhw_scheduler.async_track_time_change",
        side_effect=_fake_track,
    ):
        entry = await _setup(
            hass,
            {
                CONF_DHW_SCHEDULE_ENABLED: True,
                CONF_DHW_START_TIME: "13:00",
                CONF_DHW_END_TIME: "15:00",
            },
        )
    entry.runtime_data.coordinator.async_request_refresh = AsyncMock()
    start_cb = next(c["action"] for c in calls if c["hour"] == 13)
    end_cb = next(c["action"] for c in calls if c["hour"] == 15)


    fired = datetime(2026, 9, 16, 13, 0, tzinfo=AMS)
    with patch("custom_components.qube_heatpump.dhw_scheduler.dt_util.now", return_value=fired):
        await start_cb(None)
    await hass.async_block_till_done()

    binary = hass.states.get(BINARY_ID)
    assert binary.attributes["window_active"] is True
    assert binary.attributes["last_start"] == fired.isoformat()
    assert binary.attributes["icon"] == "mdi:water-boiler"
    after_next = hass.states.get(NEXT_START_ID).state
    assert datetime.fromisoformat(after_next) == datetime(2026, 9, 17, 13, 0, tzinfo=AMS)

    ended = datetime(2026, 9, 16, 15, 0, tzinfo=AMS)
    with patch("custom_components.qube_heatpump.dhw_scheduler.dt_util.now", return_value=ended):
        await end_cb(None)
    await hass.async_block_till_done()

    binary = hass.states.get(BINARY_ID)
    assert binary.attributes["window_active"] is False
    assert binary.attributes["last_end"] == ended.isoformat()
    assert binary.attributes["icon"] == "mdi:calendar-clock"


async def test_state_recorded_even_when_write_fails(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A failed Modbus write still records the fire so the entities stay truthful."""
    calls: list[dict] = []

    def _fake_track(hass_, action, *, hour=None, minute=None, second=None):
        calls.append({"action": action, "hour": hour})
        return MagicMock()

    with patch(
        "custom_components.qube_heatpump.dhw_scheduler.async_track_time_change",
        side_effect=_fake_track,
    ):
        entry = await _setup(
            hass,
            {CONF_DHW_SCHEDULE_ENABLED: True, CONF_DHW_START_TIME: "13:00", CONF_DHW_END_TIME: "15:00"},
        )
    mock_qube_client.write_switch.side_effect = ConnectionError("boom")
    start_cb = next(c["action"] for c in calls if c["hour"] == 13)
    await start_cb(None)
    state = entry.runtime_data.dhw_schedule
    assert state.window_active is True
    assert state.last_start is not None


# --- runtime toggle switch -------------------------------------------------------

SWITCH_ID = "switch.qube_1_dhw_schedule_enabled"


async def test_schedule_switch_reflects_option_and_updates_entry(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Turning the switch on writes the option and triggers a reload; no-op when unchanged."""
    entry = await _setup(hass, {})
    state = hass.states.get(SWITCH_ID)
    assert state is not None
    assert state.state == "off"

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload, patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        # Already off: turning off must not write anything
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": SWITCH_ID}, blocking=True
        )
        await hass.async_block_till_done()
        update.assert_not_called()
        reload.assert_not_awaited()

        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": SWITCH_ID}, blocking=True
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_DHW_SCHEDULE_ENABLED] is True
    update.assert_called_once()
    reload.assert_awaited_once_with(entry.entry_id)


async def test_schedule_switch_turn_off_when_enabled(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Turning the switch off clears the option and keeps the other schedule options."""
    with patch(
        "custom_components.qube_heatpump.dhw_scheduler.async_track_time_change",
        return_value=MagicMock(),
    ):
        entry = await _setup(
            hass,
            {
                CONF_DHW_SCHEDULE_ENABLED: True,
                CONF_DHW_START_TIME: "13:00",
                CONF_DHW_END_TIME: "15:00",
            },
        )
    assert hass.states.get(SWITCH_ID).state == "on"

    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": SWITCH_ID}, blocking=True
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_DHW_SCHEDULE_ENABLED] is False
    assert entry.options[CONF_DHW_START_TIME] == "13:00"
    reload.assert_awaited_once_with(entry.entry_id)
