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
    CONF_LABEL,
    CONF_SHOW_LABEL_IN_NAME,
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

    # Determine a short label for this hub across all entries (qube1, qube2, ...)
    label = entry.options.get(CONF_LABEL)
    if not label:
        # Assign next free qubeN label
        existing = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
        used = {e.options.get(CONF_LABEL) for e in existing if e.options.get(CONF_LABEL)}
        n = 1
        while f"qube{n}" in used:
            n += 1
        label = f"qube{n}"
        # Persist label into options (synchronous API)
        new_opts = dict(entry.options)
        new_opts[CONF_LABEL] = label
        hass.config_entries.async_update_entry(entry, options=new_opts)

    hub = WPQubeHub(hass, host, port, unit_id, label)

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
    show_label_in_name = bool(entry.options.get(CONF_SHOW_LABEL_IN_NAME, False))
    # Entity registry for conflict detection/adoption when building unique_ids
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
                # Determine best unique_id to adopt: prefer base vendor_id, but if an
                # existing entity already uses the legacy namespaced UID, adopt that to
                # avoid duplicates; otherwise suffix only on conflict.
                platform_domain = {
                    "sensor": "sensor",
                    "binary_sensor": "binary_sensor",
                    "switch": "switch",
                }.get(platform, "sensor")
                base_uid = vendor_id
                legacy_uid = f"{vendor_id}_{host}_{unit_id}"
                adopted_uid = base_uid
                # If base UID exists, adopt it
                ent_id_for_base = ent_reg.async_get_entity_id(platform_domain, DOMAIN, base_uid)
                if ent_id_for_base is not None:
                    ent_entry = ent_reg.async_get(ent_id_for_base)
                    if ent_entry and ent_entry.config_entry_id == entry.entry_id:
                        adopted_uid = base_uid
                    else:
                        # Base UID exists but belongs to a different entry: avoid adopting
                        adopted_uid = legacy_uid
                # Else if legacy UID exists, adopt legacy to attach to existing entity
                elif ent_reg.async_get_entity_id(platform_domain, DOMAIN, legacy_uid) is not None:
                    adopted_uid = legacy_uid
                else:
                    # No prior entries: only suffix if a duplicate vendor ID appears within this load
                    if vendor_id in _seen_vendor_ids.get(platform, set()):
                        adopted_uid = legacy_uid
                uid = adopted_uid
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

    # Create a Repairs issue suggesting registry migration if legacy suffixed unique_ids are detected
    try:
        from homeassistant.helpers import issue_registry as ir
        from homeassistant.helpers.issue_registry import IssueSeverity

        legacy_found = any(
            isinstance(e.unique_id, str) and e.unique_id.endswith(f"_{host}_{unit_id}")
            for e in hub.entities
        )
        if legacy_found:
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id="registry_migration_suggested",
                is_fixable=True,
                severity=IssueSeverity.WARNING,
                translation_key=None,
                translation_placeholders=None,
                learn_more_url=None,
            )
    except Exception:
        pass

    async def _async_update_data() -> dict[str, Any]:
        # Connect once per cycle; if it fails, bubble up so Coordinator marks unavailable
        await hub.async_connect()
        results: dict[str, Any] = {}
        warn_count = 0
        max_warn = 5
        for ent in hub.entities:
            try:
                val = await hub.async_read_value(ent)
            except Exception as err:
                if warn_count < max_warn:
                    logging.getLogger(__name__).warning(
                        "Read failed (%s %s@%s): %s", ent.platform, ent.input_type or ent.write_type, ent.address, err
                    )
                    warn_count += 1
                continue
            key = _entity_key(ent)
            results[key] = val
        if warn_count > max_warn:
            logging.getLogger(__name__).debug("Additional read failures suppressed in this cycle")
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
        "label": label,
        "show_label_in_name": show_label_in_name,
    }

    # Listen for options updates to apply unit/slave id without HA restart
    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        if updated_entry.entry_id != entry.entry_id:
            return
        data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if not data:
            return
        hub: WPQubeHub = data["hub"]
        coord: DataUpdateCoordinator = data["coordinator"]
        # Track current options to decide reload vs live update
        current_opts = {
            "unit_id": hub.unit,
            "use_vendor_names": bool(updated_entry.options.get(CONF_USE_VENDOR_NAMES, False)),
            "show_label_in_name": bool(updated_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False)),
        }
        new_unit = int(updated_entry.options.get(CONF_UNIT_ID, hub.unit))
        new_use_vendor = bool(updated_entry.options.get(CONF_USE_VENDOR_NAMES, False))
        new_show_label = bool(updated_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False))
        if new_unit != hub.unit and new_use_vendor == current_opts["use_vendor_names"] and new_show_label == current_opts["show_label_in_name"]:
            # Apply unit change live
            hub.set_unit_id(new_unit)
            await coord.async_request_refresh()
        else:
            # Names/display mode changed or both changed: reload to apply consistently
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    # Register a maintenance service to migrate entity registry entries
    async def _async_migrate_registry(call):
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)
        prefer_vendor_only = bool(call.data.get("prefer_vendor_only", True))
        dry_run = bool(call.data.get("dry_run", True))
        enforce_label = bool(call.data.get("enforce_label_suffix", False))
        changes = []
        for e in list(ent_reg.entities.values()):
            if e.config_entry_id != entry.entry_id:
                continue
            domain = e.domain  # sensor/binary_sensor/switch
            # Extract vendor_id and legacy suffix if present
            uid = e.unique_id
            if not isinstance(uid, str):
                continue
            parts = uid.split("_")
            # Heuristic: legacy uid ends with _<host>_<unit>
            base_uid = uid
            if len(parts) > 2 and parts[-1].isdigit():
                # Likely legacy form
                base_uid = "_".join(parts[:-2])
            # Determine desired unique_id
            desired_uid = base_uid if prefer_vendor_only else uid
            # Determine desired entity_id object id
            def _slugify(text: str) -> str:
                return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()

            suffix = data.get("label") if enforce_label else None
            desired_obj = _slugify(f"{base_uid}_{suffix}") if suffix else _slugify(base_uid)
            desired_eid = f"{domain}.{desired_obj}"
            # Skip if this entry already uses desired unique_id
            if e.unique_id == desired_uid and e.entity_id == desired_eid:
                continue
            # Check conflicts
            target_conflict = ent_reg.async_get_entity_id(domain, DOMAIN, desired_uid)
            eid_conflict = ent_reg.async_get(desired_eid)
            if target_conflict and target_conflict != e.entity_id:
                # Can't switch unique_id because target exists
                continue
            if eid_conflict and eid_conflict.entity_id != e.entity_id:
                # Can't rename entity_id because target exists
                continue
            changes.append((e.entity_id, desired_eid, e.unique_id, desired_uid))
            if not dry_run:
                # Try to update entity_id first
                try:
                    if e.entity_id != desired_eid:
                        ent_reg.async_update_entity(e.entity_id, new_entity_id=desired_eid)
                except Exception:
                    pass
                # Try to update unique_id if HA supports it
                try:
                    if e.unique_id != desired_uid:
                        ent_reg.async_update_entity(desired_eid, new_unique_id=desired_uid)  # type: ignore[arg-type]
                except Exception:
                    pass
        if changes:
            logging.getLogger(__name__).info(
                "Registry migration (%s): %s", "dry_run" if dry_run else "applied", changes
            )

    # Register service with schema for validation (also described in services.yaml)
    import voluptuous as vol
    from homeassistant.helpers import config_validation as cv
    svc_schema = vol.Schema(
        {
            vol.Optional("dry_run", default=True): cv.boolean,
            vol.Optional("prefer_vendor_only", default=True): cv.boolean,
        }
    )
    hass.services.async_register(DOMAIN, "migrate_registry", _async_migrate_registry, schema=svc_schema)

    # Service: open options flow programmatically
    async def _async_open_options(call):
        import voluptuous as vol
        from homeassistant.helpers import config_validation as cv

        schema = vol.Schema({vol.Optional("entry_id"): cv.string})
        data = schema(call.data)

        target_entry: ConfigEntry | None = None
        eid = data.get("entry_id")
        if eid:
            target_entry = hass.config_entries.async_get_entry(eid)
        else:
            # If only one entry exists for this domain, pick it
            entries = [e for e in hass.config_entries.async_entries(DOMAIN)]
            if len(entries) == 1:
                target_entry = entries[0]
        if target_entry is None:
            logging.getLogger(__name__).warning(
                "open_options: unable to determine target entry; provide entry_id"
            )
            return
        logging.getLogger(__name__).debug(
            "open_options: starting options flow for %s", target_entry.entry_id
        )
        try:
            result = await hass.config_entries.options.async_init(target_entry.entry_id)
            logging.getLogger(__name__).debug(
                "open_options: flow created: %s", result
            )
        except Exception as exc:
            logging.getLogger(__name__).error("open_options failed: %s", exc)

    # Register with a simple schema (no entity/device selector required)
    import voluptuous as vol
    hass.services.async_register(
        DOMAIN,
        "open_options",
        _async_open_options,
        schema=vol.Schema({vol.Optional("entry_id"): vol.Coerce(str)}),
    )

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


import logging
# Eagerly expose the options flow symbol at module import, matching core patterns (e.g., MQTT)
try:
    from .config_flow import async_get_options_flow as async_get_options_flow  # type: ignore[reimported]
except Exception:  # pragma: no cover
    # Fallback lazy path; HA will import this attribute when rendering Configure
    async def async_get_options_flow(config_entry: ConfigEntry):
        logging.getLogger(__name__).debug(
            "async_get_options_flow (lazy) for entry %s", config_entry.entry_id
        )
        from .config_flow import OptionsFlowHandler  # lazy import

        return OptionsFlowHandler(config_entry)
