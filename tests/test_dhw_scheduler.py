"""Tests for the Qube Heat Pump DHW (Domestic Hot Water) scheduler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

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
from custom_components.qube_heatpump.dhw_scheduler import async_setup_dhw_schedule
from custom_components.qube_heatpump.hub import QubeHub

if TYPE_CHECKING:
    import pytest

    from homeassistant.core import HomeAssistant


def _install_track_time_change_recorder() -> tuple[MagicMock, list[dict], list[MagicMock]]:
    """Build a fake async_track_time_change that records callbacks instead of scheduling.

    Returns (fake_function, calls, cancels). `calls` records the hour/minute/
    action passed for each registration in call order; `cancels` holds the
    MagicMock cancel callables returned, in the same order.
    """
    calls: list[dict] = []
    cancels: list[MagicMock] = []

    def _fake_track_time_change(hass, action, *, hour=None, minute=None, second=None):
        calls.append({"action": action, "hour": hour, "minute": minute, "second": second})
        cancel = MagicMock(name=f"cancel_{len(cancels)}")
        cancels.append(cancel)
        return cancel

    return _fake_track_time_change, calls, cancels


async def _setup_dhw_entry(
    hass: HomeAssistant, options: dict
) -> tuple[MockConfigEntry, list[dict], list[MagicMock]]:
    """Set up a config entry with the DHW schedule enabled.

    async_track_time_change is patched so that the start/end callbacks are
    captured directly instead of relying on real wall-clock scheduling.
    """
    fake_track, calls, cancels = _install_track_time_change_recorder()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options=options,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.qube_heatpump.dhw_scheduler.async_track_time_change",
        side_effect=fake_track,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry, calls, cancels


async def test_dhw_schedule_setup_returns_cancel_callbacks_with_parsed_times(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Setup should register two time-change listeners at the configured times."""
    _entry, calls, cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            CONF_DHW_SETPOINT: 55.5,
        },
    )

    assert len(cancels) == 2

    assert len(calls) == 2
    assert calls[0]["hour"] == 8
    assert calls[0]["minute"] == 15
    assert calls[0]["second"] == 0
    assert calls[1]["hour"] == 21
    assert calls[1]["minute"] == 45
    assert calls[1]["second"] == 0


async def test_dhw_schedule_start_callback_writes_setpoint_then_switch(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """With the controller-setpoint option off, write the setpoint, then the switch."""
    entry, calls, _cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            CONF_DHW_USE_CONTROLLER_SETPOINT: False,
            CONF_DHW_SETPOINT: 55.5,
        },
    )

    order: list[tuple] = []

    async def _setpoint_side_effect(key: str, value: float) -> bool:
        order.append(("setpoint", key, value))
        return True

    async def _switch_side_effect(key: str, value: bool) -> bool:
        order.append(("switch", key, value))
        return True

    mock_qube_client.write_setpoint.side_effect = _setpoint_side_effect
    mock_qube_client.write_switch.side_effect = _switch_side_effect
    entry.runtime_data.coordinator.async_request_refresh = AsyncMock(
        side_effect=lambda: order.append(("refresh",))
    )

    start_callback = calls[0]["action"]
    await start_callback(None)

    assert order == [
        ("setpoint", "tapw_timeprogram_dhwsetp_nolinq", 55.5),
        ("switch", "tapw_timeprogram_bms_forced", True),
        ("refresh",),
    ]


async def test_dhw_schedule_start_callback_default_leaves_controller_setpoint(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """By default the start callback must not touch register 173 (Modbus setpoint).

    Writing the options value before every forced run silently overrode
    whatever the user had set on the controller.
    """
    entry, calls, _cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            # A stored setpoint (e.g. from an older version) is ignored while
            # the controller-setpoint option is on (the default).
            CONF_DHW_SETPOINT: 55.5,
        },
    )

    mock_qube_client.write_setpoint.reset_mock()
    mock_qube_client.write_switch.reset_mock()
    entry.runtime_data.coordinator.async_request_refresh = AsyncMock()

    await calls[0]["action"](None)

    mock_qube_client.write_setpoint.assert_not_awaited()
    mock_qube_client.write_switch.assert_awaited_once_with(
        "tapw_timeprogram_bms_forced", True
    )


async def test_dhw_schedule_start_callback_uses_default_setpoint_when_writing(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """When a write is requested but no value is stored, the 50 °C default applies."""
    entry, calls, _cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            CONF_DHW_USE_CONTROLLER_SETPOINT: False,
        },
    )

    mock_qube_client.write_setpoint.reset_mock()
    entry.runtime_data.coordinator.async_request_refresh = AsyncMock()

    await calls[0]["action"](None)

    mock_qube_client.write_setpoint.assert_awaited_once_with(
        "tapw_timeprogram_dhwsetp_nolinq", 50.0
    )


async def test_dhw_schedule_end_callback_turns_switch_off(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """The end callback should turn the DHW force switch off."""
    entry, calls, _cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            CONF_DHW_SETPOINT: 55.5,
        },
    )

    mock_qube_client.write_switch.reset_mock()
    refresh_mock = AsyncMock()
    entry.runtime_data.coordinator.async_request_refresh = refresh_mock

    end_callback = calls[1]["action"]
    await end_callback(None)

    mock_qube_client.write_switch.assert_awaited_once_with(
        "tapw_timeprogram_bms_forced", False
    )
    refresh_mock.assert_called_once()


async def test_dhw_schedule_missing_switch_returns_empty_and_logs_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the tapw_timeprogram_bms_forced switch can't be found, bail out cleanly."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube 1")
    hub.load_library_entities()
    hub.entities = [
        ent for ent in hub.entities if ent.vendor_id != "tapw_timeprogram_bms_forced"
    ]

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        options={CONF_DHW_SCHEDULE_ENABLED: True},
    )
    coordinator = MagicMock()

    with caplog.at_level(logging.ERROR):
        result = await async_setup_dhw_schedule(hass, entry, hub, coordinator)

    assert result == []
    assert "tapw_timeprogram_bms_forced" in caplog.text


async def test_dhw_schedule_unload_cancels_callbacks(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Unloading the config entry should cancel both DHW schedule listeners."""
    entry, _calls, cancels = await _setup_dhw_entry(
        hass,
        {
            CONF_DHW_SCHEDULE_ENABLED: True,
            CONF_DHW_START_TIME: "08:15",
            CONF_DHW_END_TIME: "21:45",
            CONF_DHW_SETPOINT: 55.5,
        },
    )
    assert len(cancels) == 2

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    for cancel in cancels:
        cancel.assert_called_once()
