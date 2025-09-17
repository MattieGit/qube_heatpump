from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
import logging
from typing import Any
import re

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
    CONF_UNIT_ID,
    CONF_USE_VENDOR_NAMES,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Lazy import so the config_flow can load even if requirements
    # (e.g., pymodbus) aren't installed yet.
    from .hub import WPQubeHub, EntityDef
    import yaml
    host = entry.data[CONF_HOST]
    from .const import DEFAULT_PORT
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

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
    # Options override: allow user to set Modbus unit/slave id via Options Flow
    unit_id = int(entry.options.get(CONF_UNIT_ID, spec.get("unit_id", 1)))

    hub = WPQubeHub(hass, host, port, unit_id)

    # Optional translations for entity display names based on vendor unique_id
    def _load_name_map() -> dict[str, str]:
        lang = getattr(hass.config, "language", None) or "en"
        lang = str(lang).lower().split("-")[0]
        base = Path(__file__).parent / "translations"
        candidates = [
            base / f"entity_names.{lang}.json",
            base / "entity_names.en.json",
        ]
        for path in candidates:
            try:
                if path.exists():
                    import json
                    return {k.lower(): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
            except Exception:
                continue
        return {}

    name_map = _load_name_map()
    use_vendor_names = bool(entry.options.get(CONF_USE_VENDOR_NAMES, False))
    # Entity registry for conflict detection when building unique_ids
    from homeassistant.helpers import entity_registry as er
    ent_reg = er.async_get(hass)

    def _strip_prefix(name: str) -> str:
        # Remove leading "WP-Qube"/"WP Qube" prefix from names
        n = name.strip()
        if n.lower().startswith("wp-qube"):
            # remove the prefix and any following separators/spaces
            return re.sub(r"^\s*wp[-\s]?qube\s*", "", n, flags=re.IGNORECASE) or n
        return n

    # Track vendor IDs we have already used per platform to avoid duplicate
    # unique_id collisions within a single hub load, before the registry
    # is updated.
    _seen_vendor_ids: dict[str, set[str]] = {"sensor": set(), "binary_sensor": set(), "switch": set()}

    def _to_entity_defs(platform: str, items: list[dict[str, Any]] | None) -> list[EntityDef]:
        res: list[EntityDef] = []
        for it in items or []:
            raw_name = it.get("name", f"{platform} {it.get('address')}")
            uid = it.get("unique_id")
            vendor_id = None
            if uid:
                vendor_id = str(uid).lower()
                # Prefer base vendor_id; suffix with host+unit if (a) we already used this
                # vendor_id for this platform in this hub load, or (b) the registry reports
                # an existing entity with that unique_id.
                platform_domain = {
                    "sensor": "sensor",
                    "binary_sensor": "binary_sensor",
                    "switch": "switch",
                }.get(platform, "sensor")
                base_uid = vendor_id
                conflict = False
                if vendor_id in _seen_vendor_ids.get(platform, set()):
                    conflict = True
                if ent_reg.async_get_entity_id(platform_domain, DOMAIN, base_uid) is not None:
                    conflict = True
                uid = f"{vendor_id}_{host}_{unit_id}" if conflict else base_uid
                _seen_vendor_ids.setdefault(platform, set()).add(base_uid)
            # Prefer translated display name if available
            display_name = _strip_prefix(raw_name)
            if vendor_id and vendor_id in name_map:
                display_name = name_map[vendor_id]
            if use_vendor_names and vendor_id:
                display_name = vendor_id
            res.append(
                EntityDef(
                    platform=platform,
                    name=str(display_name).strip(),
                    vendor_id=vendor_id,
                    address=int(it["address"]),
                    input_type=it.get("input_type"),
                    write_type=it.get("write_type"),
                    data_type=it.get("data_type"),
                    unit_of_measurement=it.get("unit_of_measurement"),
                    device_class=it.get("device_class"),
                    state_class=it.get("state_class"),
                    precision=it.get("precision"),
                    unique_id=uid,
                    offset=it.get("offset"),
                    scale=it.get("scale"),
                    min_value=it.get("min_value"),
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
            try:
                val = await hub.async_read_value(ent)
            except Exception as err:
                logging.getLogger(__name__).warning(
                    "Failed reading %s @ %s: %s", ent.platform, ent.address, err
                )
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

    # Listen for options updates to apply unit/slave id without HA restart
    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        if updated_entry.entry_id != entry.entry_id:
            return
        # Reload entry so that display names and settings apply consistently
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

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


# Expose options flow handler for HA to discover Configure/Options in UI
async def async_get_options_flow(config_entry: ConfigEntry):
    # Lazy import to avoid loading config flow until needed
    from .config_flow import OptionsFlowHandler  # type: ignore

    return OptionsFlowHandler(config_entry)
