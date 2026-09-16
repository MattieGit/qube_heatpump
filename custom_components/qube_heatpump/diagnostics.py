"""Diagnostics support for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import QubeConfigEntry

# Entity unique_ids are the library register keys and stay readable so a
# diagnostics dump can be matched against the register documentation.
TO_REDACT = {"host", "port", "ip_address", "resolved_ip"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: QubeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator

    summary = {
        "entry": {
            "entry_id": entry.entry_id,
            "data": entry.data,
            "options": entry.options,
        },
        "firmware_version": data.version,
        "hub": {
            "host": hub.host,
            "port": hub.port,
            "resolved_ip": hub.resolved_ip,
            "label": hub.label,
            "multi_device": data.multi_device,
            "err_connect": hub.err_connect,
            "err_read": hub.err_read,
        },
        "entities": [
            {
                "name": ent.name,
                "unique_id": ent.unique_id,
                "platform": ent.platform,
                "address": ent.address,
            }
            for ent in hub.entities
        ],
        # Three views of the same registers: what the controller reported this
        # poll, what Home Assistant shows, and the maximum the clamp is holding.
        "raw_data": coordinator.raw_data,
        "coordinator_data": coordinator.data,
        "monotonic_cache": dict(hub.client.monotonic_cache),
        "energy_totals_stale": coordinator.energy_totals_stale,
    }
    return async_redact_data(summary, TO_REDACT)
