"""DataUpdateCoordinator for Qube Heat Pump."""

from __future__ import annotations

import contextlib
from datetime import timedelta
import logging
import math
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .entity_defs import EntityDef
    from .hub import QubeHub

from homeassistant.components.sensor import SensorStateClass
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .helpers import entity_data_key as _entity_key

# Number of consecutive failed polls before creating a repair issue
CONSECUTIVE_FAILURES_THRESHOLD = 5
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}_monotonic"
# Minimum seconds between persisting the monotonic cache to disk
SAVE_INTERVAL_SECONDS = 300

# Energy totaliser staleness detection: the electric and thermic totals
# (registers 69/71) are expected to advance while the heat pump draws real
# power. If neither has changed for this long while the electric power stays
# above the threshold, the totals are flagged as not advancing.
ENERGY_TOTAL_KEYS = ("energy_total_electric", "energy_total_thermic")
ENERGY_POWER_KEY = "power_electric"
ENERGY_STALE_POWER_THRESHOLD_W = 300.0
ENERGY_STALE_TIMEOUT_SECONDS = 15 * 60

_LOGGER = logging.getLogger(__name__)


def _needs_monotonic_clamping(ent: EntityDef) -> bool:
    """Check if an entity needs monotonic clamping.

    Energy totals and working-hour counters are mapped to
    ``total_increasing`` by entity_defs, so the state class is the only
    signal needed.
    """
    return ent.state_class == SensorStateClass.TOTAL_INCREASING


def monotonic_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, float]]:
    """Return the on-disk store holding an entry's monotonic clamp baselines."""
    return Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry_id}")


def connection_issue_id(entry_id: str) -> str:
    """Return the repair issue id used for persistent connection failures."""
    return f"connection_failed_{entry_id}"


class QubeCoordinator(TimestampDataUpdateCoordinator[dict[str, Any]]):
    """Qube Heat Pump custom coordinator."""

    config_entry: ConfigEntry
    sw_version: str | None = None

    def __init__(self, hass: HomeAssistant, hub: QubeHub, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hub = hub
        self._consecutive_failures = 0
        self._store = monotonic_store(hass, entry.entry_id)
        self._save_scheduled = False
        # Register keys that already produced a non-finite warning
        self._nonfinite_warned: set[str] = set()
        # Energy totaliser staleness tracking (see _track_energy_staleness)
        self.energy_totals_stale = False
        # Readings as the controller reported them (rounded, before monotonic
        # clamping); ``data`` holds what Home Assistant shows. Comparing the
        # two tells a stalled counter apart from the clamp holding a maximum.
        self.raw_data: dict[str, Any] = {}
        self._energy_last_values: dict[str, float] = {}
        self._energy_stale_since: float | None = None
        super().__init__(
            hass,
            _LOGGER,
            name="qube_heatpump_coordinator",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )

    async def _async_setup(self) -> None:
        """Connect to the device and read its software version.

        Raising UpdateFailed here makes async_config_entry_first_refresh
        raise ConfigEntryNotReady so Home Assistant retries the setup.
        """
        try:
            await self.hub.async_connect()
        except ConnectionError as err:
            raise UpdateFailed(
                f"Unable to connect to Qube heat pump at {self.hub.host}: {err}"
            ) from err
        # The library returns None (and logs) when the register is unreadable
        self.sw_version = await self.hub.async_get_software_version()

    async def async_shutdown(self) -> None:
        """Stop polling and flush a pending monotonic cache save.

        The base class registers this on config entry unload. Writing the
        cache now (instead of letting the delayed save fire later) prevents a
        stale write after the entry has been reloaded with a fresh client.
        """
        await super().async_shutdown()
        if self._save_scheduled:
            self._save_scheduled = False
            await self._store.async_save(dict(self.hub.client.monotonic_cache))

    def _record_failure(self, reason: str) -> UpdateFailed:
        """Count a failed poll and raise a repair issue after enough of them."""
        self._consecutive_failures += 1
        if self._consecutive_failures == CONSECUTIVE_FAILURES_THRESHOLD:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                connection_issue_id(self.config_entry.entry_id),
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="connection_failed",
                translation_placeholders={"host": self.hub.host},
            )
        return UpdateFailed(reason)

    def _record_success(self) -> None:
        """Reset the failure counter and clear any connection issue.

        Deleting is unconditional (and a no-op when there is no issue): the
        issue may have been created by a previous coordinator instance
        before a reload.
        """
        self._consecutive_failures = 0
        ir.async_delete_issue(
            self.hass, DOMAIN, connection_issue_id(self.config_entry.entry_id)
        )

    async def async_load_monotonic_cache(self) -> None:
        """Load the monotonic cache from persistent storage into the library client.

        On HA restart the in-memory monotonic cache is empty.  The first
        register reading may round to a value slightly below the last
        recorded state (float32 precision jitter), which HA then flags as
        "state is not strictly increasing".  By restoring the cache from
        disk we ensure the first reading is properly clamped.
        """
        client = self.hub.client
        if client.monotonic_cache:
            return  # Already populated

        stored = await self._store.async_load()
        if not stored or not isinstance(stored, dict):
            return

        client.monotonic_cache = stored
        _LOGGER.info("Restored monotonic cache with %d values from disk", len(stored))

    async def async_clear_monotonic_cache(self) -> None:
        """Forget all monotonic baselines, in memory and on disk, then re-poll.

        After a deliberate counter reset on the controller the clamped values
        in the cache are stale; clearing them lets the next reading through
        as the new baseline.
        """
        self.hub.client.clear_monotonic_cache()
        await self._store.async_remove()
        # async_remove cancels any pending delayed save; allow the next poll
        # to schedule a fresh one, otherwise the cache is never persisted again.
        self._save_scheduled = False
        _LOGGER.info("Monotonic cache cleared for %s", self.hub.host)
        await self.async_request_refresh()

    def _track_energy_staleness(
        self, results: dict[str, Any], now: float | None = None
    ) -> None:
        """Update ``energy_totals_stale`` from this poll's raw readings.

        Stale means: electric power above ENERGY_STALE_POWER_THRESHOLD_W for
        at least ENERGY_STALE_TIMEOUT_SECONDS while neither energy total
        changed *on the controller*. The raw (pre-clamp) values are compared,
        so a counter that stepped back slightly and is climbing again is not
        reported as stale merely because the clamp holds the old maximum for
        Home Assistant. A poll without a power reading leaves the timer
        untouched.
        """
        now = time.monotonic() if now is None else now
        advanced = False
        for key in ENERGY_TOTAL_KEYS:
            value = results.get(key)
            if not isinstance(value, (int, float)):
                continue
            if (
                key in self._energy_last_values
                and self._energy_last_values[key] != value
            ):
                advanced = True
            self._energy_last_values[key] = float(value)

        power = results.get(ENERGY_POWER_KEY)
        if advanced:
            self._energy_stale_since = None
            stale = False
        elif not isinstance(power, (int, float)):
            # Unknown power: neither evidence for nor against staleness
            stale = self.energy_totals_stale
        elif power <= ENERGY_STALE_POWER_THRESHOLD_W:
            self._energy_stale_since = None
            stale = False
        else:
            if self._energy_stale_since is None:
                self._energy_stale_since = now
            stale = now - self._energy_stale_since >= ENERGY_STALE_TIMEOUT_SECONDS

        if stale and not self.energy_totals_stale:
            _LOGGER.warning(
                "Energy totals for %s have not advanced for %d minutes while "
                "electric power is %.0f W; derived energy/SCOP sensors are stale",
                self.hub.host,
                ENERGY_STALE_TIMEOUT_SECONDS // 60,
                power,
            )
        elif self.energy_totals_stale and not stale:
            _LOGGER.info("Energy totals for %s are advancing again", self.hub.host)
        self.energy_totals_stale = stale

    def _schedule_save(self) -> None:
        """Schedule a delayed save of the monotonic cache to disk."""
        if self._save_scheduled:
            return

        client = self.hub.client

        def _get_data() -> dict[str, float]:
            self._save_scheduled = False
            return dict(client.monotonic_cache)

        self._save_scheduled = True
        self._store.async_delay_save(_get_data, SAVE_INTERVAL_SECONDS)

    def _log_nonfinite(self, ent: EntityDef, key: str, value: Any) -> None:
        """Warn once per register about a non-finite value, then log at DEBUG."""
        level = logging.DEBUG if key in self._nonfinite_warned else logging.WARNING
        self._nonfinite_warned.add(key)
        _LOGGER.log(
            level,
            "Non-finite value (%s) for %s %s@%s; treating as unavailable",
            value,
            ent.platform,
            ent.input_type or ent.write_type or "register",
            ent.address,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the hub."""
        try:
            await self.hub.async_connect()
        except ConnectionError as exc:
            raise self._record_failure(
                f"Connection to {self.hub.host} failed: {exc}"
            ) from exc

        # Fetch all values in a handful of batched block reads instead of
        # one Modbus transaction per entity (library >=1.12.0).
        try:
            bulk = await self.hub.async_get_all_entities()
        except OSError as exc:
            self.hub.inc_read_error()
            raise self._record_failure(
                f"Reading from {self.hub.host} failed: {exc}"
            ) from exc

        # The library swallows per-register errors and returns None; when
        # every register is None the device did not answer at all.
        if all(bulk.get(ent.vendor_id or "") is None for ent in self.hub.entities):
            self.hub.inc_read_error()
            raise self._record_failure(f"No data received from {self.hub.host}")

        self._record_success()

        client = self.hub.client
        results: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        for ent in self.hub.entities:
            value = bulk.get(ent.vendor_id) if ent.vendor_id else None
            key = _entity_key(ent)

            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                self._log_nonfinite(ent, key, value)
                results[key] = None
                continue

            # Round before monotonic clamping so the cache stores values at
            # the same precision Home Assistant will see.  This prevents
            # float32 jitter from producing a rounded decrease after an HA
            # restart (when the in-memory cache is empty).
            if isinstance(value, (int, float)) and ent.precision is not None:
                with contextlib.suppress(TypeError, ValueError):
                    value = round(float(value), int(ent.precision))

            raw[key] = value
            # Delegate monotonic clamping to the library client
            if _needs_monotonic_clamping(ent) and isinstance(value, (int, float)):
                value = client.clamp_monotonic(key, value)

            results[key] = value

        if client.monotonic_cache:
            self._schedule_save()

        self.raw_data = raw
        self._track_energy_staleness(raw)

        return results
