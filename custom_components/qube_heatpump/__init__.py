from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial
from pathlib import Path
import json
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
    def _load_yaml_from_path(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    data = await hass.async_add_executor_job(_load_yaml_from_path, yaml_path)

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
    async def _load_name_map() -> dict[str, str]:
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
                    loader = partial(path.read_text, encoding="utf-8")
                    text = await hass.async_add_executor_job(loader)
                    return {k.lower(): v for k, v in json.loads(text).items()}
            except Exception:
                continue
        return {}

    name_map = await _load_name_map()

    async def _async_resolve_version() -> str:
        manifest = Path(__file__).resolve().parent / "manifest.json"
        if not manifest.exists():
            return "unknown"
        try:
            loader = partial(manifest.read_text, encoding="utf-8")
            text = await hass.async_add_executor_job(loader)
            data = json.loads(text)
            version = data.get("version")
            if version:
                return str(version)
        except Exception:
            return "unknown"
        return "unknown"

    version = await _async_resolve_version()
    use_vendor_names = False
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
                legacy_uid = f"{vendor_id}_{label}"
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

    # Create or clear a Repairs issue suggesting registry migration if legacy unique_ids are detected
    try:
        from homeassistant.helpers import issue_registry as ir
        from homeassistant.helpers.issue_registry import IssueSeverity
        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(hass)
        legacy_suffix = f"_{host}_{unit_id}"
        legacy_found = False
        for ent in list(ent_reg.entities.values()):
            if ent.config_entry_id != entry.entry_id:
                continue
            if isinstance(ent.unique_id, str) and ent.unique_id.endswith(legacy_suffix):
                legacy_found = True
                break
        if legacy_found:
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id="registry_migration_suggested",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key=None,
                translation_placeholders=None,
                learn_more_url=None,
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, "registry_migration_suggested")

        # Auto-migrate known host/IP suffixed UIDs to label-suffixed UIDs for this entry
        try:
            for ent in list(ent_reg.entities.values()):
                if ent.config_entry_id != entry.entry_id:
                    continue
                uid = ent.unique_id
                if not isinstance(uid, str) or not uid.endswith(legacy_suffix):
                    continue
                # For our computed/info/reload UIDs, replace suffix with label
                if uid.startswith("wp_qube_") or uid.startswith("qube_info_sensor_") or uid.startswith("qube_reload_") or uid.startswith("wp_qube_sensor_"):
                    new_uid = uid[: -len(legacy_suffix)] + f"_{label}"
                    try:
                        ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_uid)  # type: ignore[arg-type]
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass

    # Cleanup: remove deprecated sensor for input register 63 from the entity registry
    try:
        legacy_uids = {
            "GeneralMng_TotalThermic_computed",
            f"wp_qube_sensor_{label}_input_63",
        }
        for ent in list(ent_reg.entities.values()):
            try:
                if ent.config_entry_id != entry.entry_id or ent.domain != "sensor":
                    continue
                if isinstance(ent.unique_id, str) and ent.unique_id in legacy_uids:
                    ent_reg.async_remove(ent.entity_id)
            except Exception:
                continue
    except Exception:
        pass

    # When multiple devices are configured, ensure Diagnostics entities have
    # label-suffixed unique_ids to avoid ambiguity. Do not change anything for
    # single-device setups to preserve stability.
    try:
        if multi_device:
            diag_bases = [
                "qube_info_sensor",
                "qube_metric_errors_connect",
                "qube_metric_errors_read",
                "qube_metric_count_sensors",
                "qube_metric_count_binary_sensors",
                "qube_metric_count_switches",
            ]
            for base in diag_bases:
                old_uid = base
                new_uid = f"{base}_{label}"
                try:
                    # Find entity by old unique_id for this platform/integration
                    old_ent_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_uid)
                    if not old_ent_id:
                        continue
                    ent = ent_reg.async_get(old_ent_id)
                    if not ent or ent.config_entry_id != entry.entry_id:
                        continue
                    # Skip if the target unique_id already exists or equals old
                    conflict = ent_reg.async_get_entity_id("sensor", DOMAIN, new_uid)
                    if conflict and conflict != old_ent_id:
                        continue
                    if ent.unique_id != new_uid:
                        ent_reg.async_update_entity(old_ent_id, new_unique_id=new_uid)  # type: ignore[arg-type]
                except Exception:
                    continue
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
                try:
                    hub.inc_read_error()
                except Exception:
                    pass
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

    # Determine whether multiple Qube entries exist (to decide label usage)
    try:
        other_entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
        multi_device = len(other_entries) >= 1
    except Exception:
        multi_device = False

    def _slugify(text: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()

    slug_host = _slugify(host)
    enforce_label_uid = bool(show_label_in_name or multi_device)

    # Migrate unique_ids between label-based and host-based patterns when the
    # desired mode changes (single-device setups now drop the label by default).
    try:
        ent_reg = er.async_get(hass)

        def _maybe_update(domain: str, old_uid: str, new_uid: str) -> None:
            if old_uid == new_uid:
                return
            try:
                old_ent_id = ent_reg.async_get_entity_id(domain, DOMAIN, old_uid)
            except Exception:
                return
            if not old_ent_id:
                return
            ent_entry = ent_reg.async_get(old_ent_id)
            if not ent_entry or ent_entry.config_entry_id != entry.entry_id:
                return
            conflict = ent_reg.async_get_entity_id(domain, DOMAIN, new_uid)
            if conflict and conflict != old_ent_id:
                return
            try:
                ent_reg.async_update_entity(old_ent_id, new_unique_id=new_uid)  # type: ignore[arg-type]
            except Exception:
                return

        for ent in hub.entities:
            if ent.platform != "sensor" or ent.unique_id:
                continue
            suffix = f"{ent.input_type}_{ent.address}"
            label_uid = f"wp_qube_sensor_{label}_{suffix}"
            host_uid = f"wp_qube_sensor_{slug_host}_{hub.unit}_{suffix}"
            if enforce_label_uid:
                _maybe_update("sensor", host_uid, label_uid)
            else:
                _maybe_update("sensor", label_uid, host_uid)

        computed_suffixes = [
            "status_full",
            "driewegklep_dhw_cv",
            "vierwegklep_verwarmen_koelen",
        ]
        for suffix in computed_suffixes:
            label_uid = f"wp_qube_{suffix}_{label}"
            host_uid = f"wp_qube_{suffix}_{slug_host}_{hub.unit}"
            if enforce_label_uid:
                _maybe_update("sensor", host_uid, label_uid)
            else:
                _maybe_update("sensor", label_uid, host_uid)

        # Diagnostics sensors (info + metrics)
        for kind in [
            "info_sensor",
            "metric_errors_connect",
            "metric_errors_read",
            "metric_count_sensors",
            "metric_count_binary_sensors",
            "metric_count_switches",
        ]:
            label_uid = f"qube_{kind}_{label}" if kind != "info_sensor" else f"qube_info_sensor_{label}"
            host_uid = (
                f"qube_{kind}_{slug_host}_{hub.unit}" if kind != "info_sensor" else f"qube_info_sensor_{slug_host}_{hub.unit}"
            )
            if enforce_label_uid:
                _maybe_update("sensor", host_uid, label_uid)
            else:
                _maybe_update("sensor", label_uid, host_uid)
    except Exception:
        pass

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "label": label,
        "show_label_in_name": show_label_in_name,
        "show_label_combined": bool(show_label_in_name or multi_device),
        "force_label_in_diag": bool(show_label_in_name or multi_device),
        "enforce_label_uid": enforce_label_uid,
        "multi_device": multi_device,
        "version": version,
    }

    # Ensure Reload button unique_id is label-suffixed when multiple devices
    # are configured, to avoid ambiguity across entries.
    try:
        if multi_device:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(hass)
            base = "qube_reload"
            old_ent_id = ent_reg.async_get_entity_id("button", DOMAIN, base)
            if old_ent_id:
                ent = ent_reg.async_get(old_ent_id)
                if ent and ent.config_entry_id == entry.entry_id:
                    new_uid = f"{base}_{label}"
                    conflict = ent_reg.async_get_entity_id("button", DOMAIN, new_uid)
                    if (not conflict) or (conflict == old_ent_id):
                        try:
                            ent_reg.async_update_entity(old_ent_id, new_unique_id=new_uid)  # type: ignore[arg-type]
                        except Exception:
                            pass
    except Exception:
        pass

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
            "show_label_in_name": bool(updated_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False)),
        }
        new_unit = int(updated_entry.options.get(CONF_UNIT_ID, hub.unit))
        new_show_label = bool(updated_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False))
        if new_unit != hub.unit and new_show_label == current_opts["show_label_in_name"]:
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
        prefer_vendor_only = True
        dry_run = bool(call.data.get("dry_run", True))
        enforce_label = bool(call.data.get("enforce_label_suffix", False))
        svc_label = str(call.data.get("label", label))
        data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        hub: WPQubeHub = data.get("hub", hub)  # fallback to local hub
        slug_host = _slugify(hub.host)
        default_label_suffix = bool(data.get("enforce_label_uid", False))
        use_label_suffix = bool(enforce_label or default_label_suffix)

        def _candidate_uids(ent: EntityDef) -> set[str]:
            candidates: set[str] = set()
            if ent.unique_id:
                uid_variants = {str(ent.unique_id)}
                uid_variants.add(str(ent.unique_id).lower())
                uid_variants.add(str(ent.unique_id).upper())
                candidates.update(uid_variants)
            suffix = None
            if ent.platform == "sensor":
                suffix = f"{ent.input_type}_{ent.address}"
                if suffix:
                    candidates.add(f"wp_qube_sensor_{label}_{suffix}")
                    candidates.add(f"wp_qube_sensor_{slug_host}_{hub.unit}_{suffix}")
            elif ent.platform == "binary_sensor":
                suffix = f"{ent.input_type}_{ent.address}"
                if suffix:
                    candidates.add(f"wp_qube_binary_{hub.host}_{hub.unit}_{suffix}")
                    candidates.add(f"wp_qube_binary_{slug_host}_{hub.unit}_{suffix}")
            elif ent.platform == "switch":
                suffix = f"{ent.write_type}_{ent.address}"
                if suffix:
                    candidates.add(f"wp_qube_switch_{hub.host}_{hub.unit}_{suffix}")
                    candidates.add(f"wp_qube_switch_{slug_host}_{hub.unit}_{suffix}")
            return {c for c in candidates if c}

        lookup: dict[tuple[str, str], EntityDef] = {}
        friendly_lookup: dict[tuple[str, str], EntityDef] = {}
        for ent_def in getattr(hub, "entities", []):
            dom = ent_def.platform
            for key in _candidate_uids(ent_def):
                lookup[(dom, key)] = ent_def
            # include coordinator key fallback
            lookup[(dom, _entity_key(ent_def))] = ent_def
            if ent_def.name:
                for variant in {
                    str(ent_def.name),
                    str(ent_def.name).lower(),
                    _slugify(str(ent_def.name)),
                }:
                    friendly_lookup[(dom, variant)] = ent_def

        changes = []
        async def _async_clear_statistics(stat_ids: set[str]) -> None:
            if not stat_ids:
                return
            try:
                from homeassistant.components import recorder
            except ImportError:
                return
            try:
                instance = recorder.get_instance(hass)
            except Exception:
                return
            if instance is None or not hasattr(instance, "async_clear_statistics"):
                return
            try:
                event = asyncio.Event()
                instance.async_clear_statistics(list(stat_ids), on_done=event.set)
                await event.wait()
            except Exception:
                pass

        for e in list(ent_reg.entities.values()):
            if e.config_entry_id != entry.entry_id:
                continue
            domain = e.domain  # sensor/binary_sensor/switch
            # Extract vendor_id and legacy suffix if present
            uid = e.unique_id
            if not isinstance(uid, str):
                continue
            ent_def = lookup.get((domain, uid))
            matched_via = "unique"
            if not ent_def:
                ent_def = friendly_lookup.get((domain, uid))
                if ent_def:
                    matched_via = "friendly"
            if not ent_def or not getattr(ent_def, "unique_id", None):
                continue
            ent_unique = str(ent_def.unique_id)
            desired_uid = ent_unique
            unique_slug_seed = ent_unique

            def _slugify(text: str) -> str:
                return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()

            base_entity = unique_slug_seed

            suffix = svc_label if enforce_label else (label if use_label_suffix else None)
            if suffix and base_entity.lower().endswith(f"_{suffix.lower()}"):
                suffix = None
            base_slug = _slugify(base_entity)
            if suffix:
                base_slug = f"{base_slug}_{_slugify(suffix)}"
            desired_eid = f"{domain}.{base_slug}"
            # Skip if this entry already uses desired unique_id
            if e.unique_id == desired_uid and e.entity_id == desired_eid:
                continue
            logging.getLogger(__name__).debug(
                "registry migrate candidate: %s (uid=%s) -> %s (uid=%s) via=%s",
                e.entity_id,
                e.unique_id,
                desired_eid,
                desired_uid,
                matched_via,
            )
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
                stats_to_clear: set[str] = set()
                if e.entity_id != desired_eid:
                    stats_to_clear.add(e.entity_id)
                    stats_to_clear.add(desired_eid)
                await _async_clear_statistics(stats_to_clear)
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
                "Registry migration (%s): %s",
                "dry_run" if dry_run else "applied",
                [
                    {
                        "entity_id": old_eid,
                        "new_entity_id": new_eid,
                        "old_unique_id": old_uid,
                        "new_unique_id": new_uid,
                    }
                    for (old_eid, new_eid, old_uid, new_uid) in changes
                ],
            )

    # Register service with schema for validation (also described in services.yaml)
    import voluptuous as vol
    from homeassistant.helpers import config_validation as cv
    svc_schema = vol.Schema(
        {
            vol.Optional("dry_run", default=True): cv.boolean,
            vol.Optional("enforce_label_suffix", default=False): cv.boolean,
            vol.Optional("label"): cv.string,
        }
    )
    hass.services.async_register(DOMAIN, "migrate_registry", _async_migrate_registry, schema=svc_schema)

    # Remove options-related services; per-device entities replace configuration
    # Service: start reconfigure flow to change host/port via modal (if supported)
    import voluptuous as vol

    async def _async_reconfigure(call):
        from homeassistant.config_entries import SOURCE_RECONFIGURE
        data = vol.Schema({vol.Optional("entry_id"): str})(call.data)
        target_entry: ConfigEntry | None = None
        eid = data.get("entry_id")
        if eid:
            target_entry = hass.config_entries.async_get_entry(eid)
        else:
            entries = [e for e in hass.config_entries.async_entries(DOMAIN)]
            if len(entries) == 1:
                target_entry = entries[0]
        if not target_entry:
            logging.getLogger(__name__).warning("reconfigure: no entry resolved; pass entry_id")
            return
        try:
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_RECONFIGURE, "entry_id": target_entry.entry_id},
                data={"entry_id": target_entry.entry_id},
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("reconfigure flow not available: %r", exc)

    hass.services.async_register(
        DOMAIN, "reconfigure", _async_reconfigure, schema=vol.Schema({vol.Optional("entry_id"): str})
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
