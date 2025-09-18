from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN

TO_REDACT = {"host", "ip", "address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    hub = data.get("hub")
    label = data.get("label")
    # Build a minimal diagnostics snapshot
    summary: dict[str, Any] = {
        "label": getattr(hub, "label", label),
        "host": getattr(hub, "host", None),
        "unit": getattr(hub, "unit", None),
        "entity_counts": {
            "sensor": sum(1 for e in getattr(hub, "entities", []) if e.platform == "sensor"),
            "binary_sensor": sum(1 for e in getattr(hub, "entities", []) if e.platform == "binary_sensor"),
            "switch": sum(1 for e in getattr(hub, "entities", []) if e.platform == "switch"),
        },
        "entities_sample": [
            {
                "platform": e.platform,
                "vendor_id": getattr(e, "vendor_id", None),
                "address": e.address,
                "input_type": e.input_type,
                "data_type": e.data_type,
            }
            for e in list(getattr(hub, "entities", []))[:10]
        ],
    }
    return async_redact_data(summary, TO_REDACT)

