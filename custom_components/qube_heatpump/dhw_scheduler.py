"""DHW (Domestic Hot Water) scheduler for Qube Heat Pump."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DHW_END_TIME,
    CONF_DHW_SCHEDULE_ENABLED,
    CONF_DHW_SETPOINT,
    CONF_DHW_START_TIME,
    CONF_DHW_USE_CONTROLLER_SETPOINT,
    DEFAULT_DHW_END_TIME,
    DEFAULT_DHW_SETPOINT,
    DEFAULT_DHW_START_TIME,
    DEFAULT_DHW_USE_CONTROLLER_SETPOINT,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .entity_defs import EntityDef
    from .hub import QubeHub

_LOGGER = logging.getLogger(__name__)

SetpointSource = Literal["controller", "fixed"]


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute)."""
    parts = str(time_str).split(":")
    return int(parts[0]), int(parts[1])


def next_occurrence(now: datetime, hour: int, minute: int) -> datetime:
    """Return the next moment at local wall-clock ``hour:minute`` strictly after ``now``.

    ``now`` must be timezone-aware. Wall-clock arithmetic is used on purpose so
    the result stays at the configured local time across DST changes, matching
    how ``async_track_time_change`` fires.
    """
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _in_window(now: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    """Return True if the local time of ``now`` lies in [start, end).

    Windows that cross midnight (e.g. 22:00-06:00) are supported.
    """
    current = (now.hour, now.minute)
    if start <= end:
        return start <= current < end
    return current >= start or current < end


@dataclass
class DhwScheduleState:
    """Observable state of the DHW schedule, exposed through entities.

    Entities subscribe with :meth:`async_add_listener`; the scheduler calls
    :meth:`async_update_listeners` after every change.
    """

    enabled: bool = False
    start_time: str | None = None
    end_time: str | None = None
    setpoint_source: SetpointSource | None = None
    fixed_setpoint: float | None = None
    window_active: bool = False
    next_start: datetime | None = None
    next_end: datetime | None = None
    last_start: datetime | None = None
    last_end: datetime | None = None
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any], now: datetime | None = None
    ) -> DhwScheduleState:
        """Build the initial state from config-entry options."""
        if not options.get(CONF_DHW_SCHEDULE_ENABLED):
            return cls()

        now = now or dt_util.now()
        start_time = str(options.get(CONF_DHW_START_TIME, DEFAULT_DHW_START_TIME))
        end_time = str(options.get(CONF_DHW_END_TIME, DEFAULT_DHW_END_TIME))
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        use_controller = bool(
            options.get(
                CONF_DHW_USE_CONTROLLER_SETPOINT, DEFAULT_DHW_USE_CONTROLLER_SETPOINT
            )
        )
        return cls(
            enabled=True,
            start_time=f"{start[0]:02d}:{start[1]:02d}",
            end_time=f"{end[0]:02d}:{end[1]:02d}",
            setpoint_source="controller" if use_controller else "fixed",
            fixed_setpoint=(
                None
                if use_controller
                else float(options.get(CONF_DHW_SETPOINT, DEFAULT_DHW_SETPOINT))
            ),
            window_active=_in_window(now, start, end),
            next_start=next_occurrence(now, *start),
            next_end=next_occurrence(now, *end),
        )

    @property
    def start(self) -> tuple[int, int] | None:
        """Configured start as (hour, minute)."""
        return _parse_time(self.start_time) if self.start_time else None

    @property
    def end(self) -> tuple[int, int] | None:
        """Configured end as (hour, minute)."""
        return _parse_time(self.end_time) if self.end_time else None

    def record_start(self, now: datetime) -> None:
        """Record that the start callback fired."""
        self.window_active = True
        self.last_start = now
        self._recompute_next(now)

    def record_end(self, now: datetime) -> None:
        """Record that the end callback fired."""
        self.window_active = False
        self.last_end = now
        self._recompute_next(now)

    def _recompute_next(self, now: datetime) -> None:
        if self.start is not None:
            self.next_start = next_occurrence(now, *self.start)
        if self.end is not None:
            self.next_end = next_occurrence(now, *self.end)

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to state changes; returns an unsubscribe callable."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    @callback
    def async_update_listeners(self) -> None:
        """Notify all subscribed entities."""
        for listener in list(self._listeners):
            listener()


async def async_setup_dhw_schedule(
    hass: HomeAssistant,
    entry: ConfigEntry,
    hub: QubeHub,
    coordinator: Any,
    state: DhwScheduleState | None = None,
) -> list[Callable[[], None]]:
    """Set up DHW schedule and return cancel callbacks.

    ``state`` is the shared state holder (``runtime_data.dhw_schedule``); it is
    built from the options when not supplied. Nothing is registered when the
    schedule is disabled.
    """
    options = dict(entry.options)
    if state is None:
        state = DhwScheduleState.from_options(options)

    if not state.enabled:
        _LOGGER.info("DHW schedule disabled")
        return []

    start_hour, start_minute = state.start or _parse_time(DEFAULT_DHW_START_TIME)
    end_hour, end_minute = state.end or _parse_time(DEFAULT_DHW_END_TIME)
    # None means: leave the Modbus DHW setpoint (register 173) untouched and
    # let the forced run use whatever is configured on the controller.
    setpoint: float | None = state.fixed_setpoint

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
        if setpoint is None:
            _LOGGER.info("DHW schedule: starting DHW heating (controller setpoint)")
        else:
            _LOGGER.info("DHW schedule: starting DHW heating (setpoint=%.1f)", setpoint)
        try:
            await hub.async_connect()
            if setpoint is not None and dhw_setpoint_ent is not None:
                await hub.async_write_setpoint(dhw_setpoint_ent, setpoint)
            await hub.async_write_switch(dhw_switch_ent, True)
            await coordinator.async_request_refresh()
        except OSError as exc:  # ConnectionError from the hub is an OSError
            _LOGGER.warning("DHW schedule: failed to start DHW heating: %s", exc)
        finally:
            state.record_start(dt_util.now())
            state.async_update_listeners()

    async def _dhw_end(_now: Any) -> None:
        """Turn off DHW heating at the scheduled end time."""
        _LOGGER.info("DHW schedule: stopping DHW heating")
        try:
            await hub.async_connect()
            await hub.async_write_switch(dhw_switch_ent, False)
            await coordinator.async_request_refresh()
        except OSError as exc:
            _LOGGER.warning("DHW schedule: failed to stop DHW heating: %s", exc)
        finally:
            state.record_end(dt_util.now())
            state.async_update_listeners()

    cancel_start = async_track_time_change(
        hass, _dhw_start, hour=start_hour, minute=start_minute, second=0
    )
    cancel_end = async_track_time_change(
        hass, _dhw_end, hour=end_hour, minute=end_minute, second=0
    )

    _LOGGER.info(
        "DHW schedule enabled %s-%s, setpoint source: %s",
        state.start_time,
        state.end_time,
        "controller Modbus setpoint"
        if setpoint is None
        else f"fixed {setpoint:.1f}°C",
    )

    return [cancel_start, cancel_end]
