"""DHW (Domestic Hot Water) scheduler for Qube Heat Pump."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.event import async_track_time_change

from .const import (
    CONF_DHW_END_TIME,
    CONF_DHW_SETPOINT,
    CONF_DHW_START_TIME,
    DEFAULT_DHW_END_TIME,
    DEFAULT_DHW_SETPOINT,
    DEFAULT_DHW_START_TIME,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .hub import EntityDef, QubeHub

_LOGGER = logging.getLogger(__name__)


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute)."""
    parts = str(time_str).split(":")
    return int(parts[0]), int(parts[1])


async def async_setup_dhw_schedule(
    hass: HomeAssistant,
    entry: ConfigEntry,
    hub: QubeHub,
    coordinator: Any,
) -> list[Callable]:
    """Set up DHW schedule and return cancel callbacks."""
    options = dict(entry.options)

    start_time_str = options.get(CONF_DHW_START_TIME, DEFAULT_DHW_START_TIME)
    end_time_str = options.get(CONF_DHW_END_TIME, DEFAULT_DHW_END_TIME)
    setpoint = float(options.get(CONF_DHW_SETPOINT, DEFAULT_DHW_SETPOINT))

    start_hour, start_minute = _parse_time(start_time_str)
    end_hour, end_minute = _parse_time(end_time_str)

    # Find DHW entities
    dhw_setpoint_ent: EntityDef | None = None
    dhw_switch_ent: EntityDef | None = None
    for ent in hub.entities:
        if ent.vendor_id == "tapw_timeprogram_dhwsetp_nolinq":
            dhw_setpoint_ent = ent
        elif ent.vendor_id == "tapw_timeprogram_bms_forced" and ent.platform == "switch":
            dhw_switch_ent = ent

    if dhw_switch_ent is None:
        _LOGGER.error("Cannot find tapw_timeprogram_bms_forced switch; DHW schedule not set up")
        return []

    async def _dhw_start(_now: Any) -> None:
        """Turn on DHW heating at the scheduled start time."""
        _LOGGER.info("DHW schedule: starting DHW heating (setpoint=%.1f)", setpoint)
        try:
            await hub.async_connect()
            if dhw_setpoint_ent is not None:
                await hub.async_write_setpoint(dhw_setpoint_ent, setpoint)
            await hub.async_write_switch(dhw_switch_ent, True)
            await coordinator.async_request_refresh()
        except Exception:
            _LOGGER.exception("DHW schedule: failed to start DHW heating")

    async def _dhw_end(_now: Any) -> None:
        """Turn off DHW heating at the scheduled end time."""
        _LOGGER.info("DHW schedule: stopping DHW heating")
        try:
            await hub.async_connect()
            await hub.async_write_switch(dhw_switch_ent, False)
            await coordinator.async_request_refresh()
        except Exception:
            _LOGGER.exception("DHW schedule: failed to stop DHW heating")

    cancel_start = async_track_time_change(
        hass, _dhw_start, hour=start_hour, minute=start_minute, second=0
    )
    cancel_end = async_track_time_change(
        hass, _dhw_end, hour=end_hour, minute=end_minute, second=0
    )

    _LOGGER.info(
        "DHW schedule configured: %02d:%02d-%02d:%02d at %.1f%sC",
        start_hour,
        start_minute,
        end_hour,
        end_minute,
        setpoint,
        "\u00b0",
    )

    return [cancel_start, cancel_end]
