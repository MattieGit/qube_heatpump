"""DataUpdateCoordinator for Qube Heat Pump."""

from __future__ import annotations

from datetime import timedelta
import logging
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .hub import EntityDef, QubeHub

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

# Number of consecutive failures before creating a repair issue
CONSECUTIVE_FAILURES_THRESHOLD = 5

_LOGGER = logging.getLogger(__name__)


def _is_working_hours_entity(ent: EntityDef) -> bool:
    """Detect working hours counters that should never decrease."""
    try:
        name = str(ent.name or "").strip().lower()
        vendor = str(ent.vendor_id or "").strip().lower()
    except (TypeError, ValueError, AttributeError):
        return False
    if name.startswith("bedrijfsuren"):
        return True
    return bool(vendor.startswith("workinghours"))


def _entity_key(ent: EntityDef) -> str:
    """Generate a key for the coordinator data."""
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


class QubeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Qube Heat Pump custom coordinator."""

    def __init__(self, hass: HomeAssistant, hub: QubeHub, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hub = hub
        self.entry = entry
        self._consecutive_failures = 0
        self._issue_created = False
        super().__init__(
            hass,
            _LOGGER,
            name="qube_heatpump_coordinator",
            update_method=self._async_update_data,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the hub."""
        try:
            await self.hub.async_resolve_ip()
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

        results: dict[str, Any] = {}

        # Access persistent storage for monotonic counters
        # We store it in hass.data[DOMAIN][entry_id] in __init__, but better to keep it here?
        # Actually __init__ setup creates the dict.
        # Let's rely on self.entry.entry_id
        domain_data = self.hass.data.get(DOMAIN, {})
        entry_store = domain_data.get(self.entry.entry_id)
        if not entry_store:
            # Should not happen if initialized correctly, but safety fallback
            entry_store = domain_data.setdefault(self.entry.entry_id, {})

        monotonic_cache: dict[str, Any] = entry_store.setdefault("monotonic_totals", {})
        warn_count = 0
        warn_cap = 5

        for ent in self.hub.entities:
            try:
                value = await self.hub.async_read_value(ent)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                self.hub.inc_read_error()
                if warn_count < warn_cap:
                    _LOGGER.warning(
                        "Read failed (%s %s@%s): %s",
                        ent.platform,
                        ent.input_type or ent.write_type,
                        ent.address,
                        exc,
                    )
                    warn_count += 1
                continue

            key = _entity_key(ent)
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                if warn_count < warn_cap:
                    _LOGGER.warning(
                        "Non-finite value (%s) for %s %s@%s; treating as unavailable",
                        value,
                        ent.platform,
                        ent.input_type or ent.write_type or "register",
                        ent.address,
                    )
                    warn_count += 1
                results[key] = None
                continue

            # Round before monotonic clamping so the cache stores values at
            # the same precision Home Assistant will see.  This prevents
            # float32 jitter from producing a rounded decrease after an HA
            # restart (when the in-memory cache is empty).
            if (
                isinstance(value, (int, float))
                and ent.precision is not None
            ):
                try:
                    value = round(float(value), int(ent.precision))
                except (TypeError, ValueError):
                    pass

            if (
                ent.state_class == "total_increasing"
                and isinstance(value, (int, float))
            ) or (_is_working_hours_entity(ent) and isinstance(value, (int, float))):
                last_value = monotonic_cache.get(key)
                if isinstance(last_value, (int, float)) and value < (last_value - 1e-6):
                    # Monotonicity violation (heat pump glitch) -> keep old value
                    _LOGGER.debug(
                        "Monotonic clamp: %s reported %s but previous was %s; keeping %s",
                        key,
                        value,
                        last_value,
                        last_value,
                    )
                    value = last_value
                else:
                    monotonic_cache[key] = value

            results[key] = value

        if warn_count > warn_cap:
            _LOGGER.debug("Additional read failures suppressed in this cycle")

        return results
