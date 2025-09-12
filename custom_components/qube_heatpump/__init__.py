from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_SCAN_INTERVAL,
    CONF_FILE_NAME,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Lazy import so the config_flow can load even if requirements
    # (e.g., pymodbus) aren't installed yet.
    from .hub import WPQubeHub, EntityDef
    import yaml
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    hub = WPQubeHub(hass, host, port)

    # Load YAML spec bundled with the integration
    # Prefer bundled YAML; fall back to repo root if not found
    yaml_path = Path(__file__).parent / CONF_FILE_NAME
    if not yaml_path.exists():
        yaml_path = Path(__file__).resolve().parents[2] / CONF_FILE_NAME
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # The YAML may contain a list with one dict
    spec = data[0] if isinstance(data, list) and data else data
    # Override host/port from config entry
    spec["host"] = host
    spec["port"] = port

    def _to_entity_defs(platform: str, items: list[dict[str, Any]] | None) -> list[EntityDef]:
        res: list[EntityDef] = []
        for it in items or []:
            res.append(
                EntityDef(
                    platform=platform,
                    name=it.get("name", f"{platform} {it.get('address')}").strip(),
                    address=int(it["address"]),
                    input_type=it.get("input_type"),
                    write_type=it.get("write_type"),
                    data_type=it.get("data_type"),
                    unit_of_measurement=it.get("unit_of_measurement"),
                    device_class=it.get("device_class"),
                    state_class=it.get("state_class"),
                    precision=it.get("precision"),
                    unique_id=it.get("unique_id"),
                    offset=it.get("offset"),
                    scale=it.get("scale"),
                )
            )
        return res

    hub.entities.extend(_to_entity_defs("binary_sensor", spec.get("binary_sensors")))
    hub.entities.extend(_to_entity_defs("sensor", spec.get("sensors")))
    hub.entities.extend(_to_entity_defs("switch", spec.get("switches")))

    async def _async_update_data() -> dict[str, Any]:
        await hub.async_connect()
        results: dict[str, Any] = {}
        for ent in hub.entities:
            # Only sensors and binary sensors are part of polling. Switches read coil state as well.
            try:
                val = await hub.async_read_value(ent)
            except Exception:
                # On failure, leave the last value untouched by not setting it
                continue
            key = _entity_key(ent)
            results[key] = val
        return results

    coordinator = DataUpdateCoordinator(
        hass,
        logger=logging.getLogger(__name__),
        name="wp_qube_coordinator",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
    }

    # Initial refresh
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (hub := data.get("hub")):
        await hub.async_close()
    return unload_ok


def _entity_key(ent: EntityDef) -> str:
    # Build a deterministic key for coordinator storage
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"
