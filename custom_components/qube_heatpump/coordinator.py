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

# Number of consecutive failures before creating a repair issue
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


class QubeCoordinator(TimestampDataUpdateCoordinator[dict[str, Any]]):
    """Qube Heat Pump custom coordinator."""

    def __init__(self, hass: HomeAssistant, hub: QubeHub, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hub = hub
        self.entry = entry
        self._consecutive_failures = 0
        self._issue_created = False
        self._store: Store[dict[str, float]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{entry.entry_id}",
        )
        self._save_scheduled = False
        # Energy totaliser staleness tracking (see _track_energy_staleness)
        self.energy_totals_stale = False
        self._energy_last_values: dict[str, float] = {}
        self._energy_stale_since: float | None = None
        super().__init__(
            hass,
            _LOGGER,
            name="qube_heatpump_coordinator",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )

    def _create_connection_issue(self) -> None:
        """Create a repair issue for persistent connection failures."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"connection_failed_{self.entry.entry_id}",
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="connection_failed",
            translation_placeholders={"host": self.hub.host},
            data={"entry_id": self.entry.entry_id},
        )
        self._issue_created = True

    def _delete_connection_issue(self) -> None:
        """Delete the connection failure repair issue."""
        if self._issue_created:
            ir.async_delete_issue(
                self.hass,
                DOMAIN,
                f"connection_failed_{self.entry.entry_id}",
            )
            self._issue_created = False

    async def async_load_monotonic_cache(self) -> None:
        """Load the monotonic cache from persistent storage into the library client.

        On HA restart the in-memory monotonic cache is empty.  The first
        register reading may round to a value slightly below the last
        recorded state (float32 precision jitter), which HA then flags as
        "state is not strictly increasing".  By restoring the cache from
        disk we ensure the first reading is properly clamped.
        """
        client = self.hub.client
        if client is not None and client.monotonic_cache:
            return  # Already populated

        stored = await self._store.async_load()
        if not stored or not isinstance(stored, dict):
            return

        if client is not None:
            client.monotonic_cache = stored
        _LOGGER.info(
            "Restored monotonic cache with %d values from disk", len(stored)
        )

    async def async_clear_monotonic_cache(self) -> None:
        """Forget all monotonic baselines, in memory and on disk, then re-poll.

        After a deliberate counter reset on the controller the clamped values
        in the cache are stale; clearing them lets the next reading through
        as the new baseline.
        """
        client = self.hub.client
        if client is not None:
            client.clear_monotonic_cache()
        await self._store.async_remove()
        # async_remove cancels any pending delayed save; allow the next poll
        # to schedule a fresh one, otherwise the cache is never persisted again.
        self._save_scheduled = False
        _LOGGER.info("Monotonic cache cleared for %s", self.hub.host)
        await self.async_request_refresh()

    def _track_energy_staleness(
        self, results: dict[str, Any], now: float | None = None
    ) -> None:
        """Update ``energy_totals_stale`` from this poll's results.

        Stale means: electric power above ENERGY_STALE_POWER_THRESHOLD_W for
        at least ENERGY_STALE_TIMEOUT_SECONDS while neither energy total
        changed. The values compared are the ones Home Assistant sees (after
        monotonic clamping), because those feed every derived day/month/SCOP
        sensor.
        """
        now = time.monotonic() if now is None else now
        advanced = False
        for key in ENERGY_TOTAL_KEYS:
            value = results.get(key)
            if not isinstance(value, (int, float)):
                continue
            if key in self._energy_last_values and self._energy_last_values[key] != value:
                advanced = True
            self._energy_last_values[key] = float(value)

        power = results.get(ENERGY_POWER_KEY)
        drawing_power = (
            isinstance(power, (int, float)) and power > ENERGY_STALE_POWER_THRESHOLD_W
        )

        if advanced or not drawing_power:
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
            if client is not None:
                return dict(client.monotonic_cache)
            return {}

        self._save_scheduled = True
        self._store.async_delay_save(_get_data, SAVE_INTERVAL_SECONDS)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the hub."""
        try:
            await self.hub.async_connect()
        except Exception as exc:
            self._consecutive_failures += 1
            if (
                self._consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD
                and not self._issue_created
            ):
                self._create_connection_issue()
            raise UpdateFailed(f"Connection to {self.hub.host} failed: {exc}") from exc

        # Connection successful - reset failure counter and delete any issue
        self._consecutive_failures = 0
        self._delete_connection_issue()

        client = self.hub.client
        results: dict[str, Any] = {}
        nonfinite_count = 0
        warn_cap = 5

        # Fetch all values in a handful of batched block reads instead of
        # one Modbus transaction per entity (library >=1.12.0).
        try:
            bulk = await self.hub.async_get_all_entities()
        except Exception as exc:
            self.hub.inc_read_error()
            raise UpdateFailed(
                f"Reading from {self.hub.host} failed: {exc}"
            ) from exc

        for ent in self.hub.entities:
            value = bulk.get(ent.vendor_id) if ent.vendor_id else None

            key = _entity_key(ent)
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                nonfinite_count += 1
                if nonfinite_count <= warn_cap:
                    _LOGGER.warning(
                        "Non-finite value (%s) for %s %s@%s; treating as unavailable",
                        value,
                        ent.platform,
                        ent.input_type or ent.write_type or "register",
                        ent.address,
                    )
                results[key] = None
                continue

            # Round before monotonic clamping so the cache stores values at
            # the same precision Home Assistant will see.  This prevents
            # float32 jitter from producing a rounded decrease after an HA
            # restart (when the in-memory cache is empty).
            if isinstance(value, (int, float)) and ent.precision is not None:
                with contextlib.suppress(TypeError, ValueError):
                    value = round(float(value), int(ent.precision))

            # Delegate monotonic clamping to the library client
            if (
                _needs_monotonic_clamping(ent)
                and isinstance(value, (int, float))
                and client is not None
            ):
                value = client.clamp_monotonic(key, value)

            results[key] = value

        if client is not None and client.monotonic_cache:
            self._schedule_save()

        self._track_energy_staleness(results)

        if nonfinite_count > warn_cap:
            _LOGGER.debug(
                "%d additional non-finite values suppressed this cycle",
                nonfinite_count - warn_cap,
            )

        return results
