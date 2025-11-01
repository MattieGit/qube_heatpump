from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import async_get_integration, async_get_loaded_integration

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    CONF_FILE_NAME,
    CONF_UNIT_ID,
    CONF_LABEL,
    CONF_SHOW_LABEL_IN_NAME,
    CONF_FRIENDLY_NAME_LANGUAGE,
    DEFAULT_FRIENDLY_NAME_LANGUAGE,
    SUPPORTED_FRIENDLY_NAME_LANGUAGES,
)

if TYPE_CHECKING:
    from .hub import EntityDef


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .hub import WPQubeHub, EntityDef  # Lazy import to avoid optional deps
    import yaml

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    yaml_path = Path(__file__).parent / CONF_FILE_NAME
    if not yaml_path.exists():
        yaml_path = Path(__file__).resolve().parents[2] / CONF_FILE_NAME

    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def _load_name_translations(language: str) -> dict[str, str]:
        translations_dir = Path(__file__).parent / "translations"
        path = translations_dir / f"entity_names.{language}.json"
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                content = json.load(handle)
        except FileNotFoundError:
            return {}
        except Exception as exc:  # pragma: no cover - defensive log
            _LOGGER.warning("Failed to load name translations for %s: %s", language, exc)
            return {}
        if not isinstance(content, dict):
            return {}
        return {str(key).lower(): str(value) for key, value in content.items() if isinstance(value, str)}

    raw_spec = await hass.async_add_executor_job(_load_yaml, yaml_path)
    spec = raw_spec[0] if isinstance(raw_spec, list) and raw_spec else raw_spec
    spec = dict(spec)
    spec["host"] = host
    spec["port"] = port
    options = dict(entry.options)
    options_changed = False

    friendly_lang = options.get(CONF_FRIENDLY_NAME_LANGUAGE, DEFAULT_FRIENDLY_NAME_LANGUAGE)
    if friendly_lang not in SUPPORTED_FRIENDLY_NAME_LANGUAGES:
        friendly_lang = DEFAULT_FRIENDLY_NAME_LANGUAGE
    if options.get(CONF_FRIENDLY_NAME_LANGUAGE) != friendly_lang:
        options[CONF_FRIENDLY_NAME_LANGUAGE] = friendly_lang
        options_changed = True

    unit_id = int(options.get(CONF_UNIT_ID, spec.get("unit_id", 1)))

    existing_entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    multi_device = len(existing_entries) >= 1

    label = options.get(CONF_LABEL)
    if not label:
        used_labels = {
            e.options.get(CONF_LABEL) for e in existing_entries if e.options.get(CONF_LABEL)
        }
        idx = 1
        while f"qube{idx}" in used_labels:
            idx += 1
        label = f"qube{idx}"
        options[CONF_LABEL] = label
        options_changed = True

    show_label_option = bool(options.get(CONF_SHOW_LABEL_IN_NAME, False))
    if multi_device and not show_label_option:
        options[CONF_SHOW_LABEL_IN_NAME] = True
        show_label_option = True
        options_changed = True

    if options_changed:
        hass.config_entries.async_update_entry(entry, options=options)

    hub = WPQubeHub(hass, host, port, unit_id, label)
    name_translations = await hass.async_add_executor_job(
        _load_name_translations, friendly_lang
    )
    hub.set_name_translations(friendly_lang, name_translations)
    await hub.async_resolve_ip()

    def _lookup_translation(*keys: str | None) -> str | None:
        for key in keys:
            if not key:
                continue
            hit = name_translations.get(str(key).lower())
            if hit:
                return hit
        return None

    def _compute_display_name(
        platform: str,
        address: int,
        provided: Any,
        vendor_id: str | None,
        translation_key: str | None = None,
    ) -> str:
        provided_clean = provided.strip() if isinstance(provided, str) else None
        candidate_slug = _slugify(provided_clean) if provided_clean else None
        translated = _lookup_translation(vendor_id, translation_key, candidate_slug)
        if translated:
            return translated
        if provided_clean:
            return provided_clean
        if vendor_id:
            return vendor_id
        return f"{platform} {address}"

    def _slugify(text: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()

    def _unique_id_for(
        platform: str,
        item: dict[str, Any],
        vendor_id: str | None,
    ) -> str:
        if vendor_id:
            base = vendor_id.lower()
            return f"{base}_{label}" if multi_device else base
        input_type = str(item.get("input_type") or item.get("write_type") or "value")
        address = item.get("address")
        suffix = f"{platform}_{input_type}_{address}".lower()
        return f"{suffix}_{label}" if multi_device else suffix

    def _to_entity_defs(platform: str, items: list[dict[str, Any]] | None) -> list[EntityDef]:
        entities: list[EntityDef] = []
        for item in items or []:
            try:
                address = int(item["address"])
            except (KeyError, TypeError, ValueError):
                continue
            vendor_id_raw = item.get("unique_id")
            vendor_id = str(vendor_id_raw).strip() if vendor_id_raw else None
            vendor_id_norm = vendor_id.lower() if vendor_id else None
            unique_id = _unique_id_for(platform, item, vendor_id_norm)
            display_name = _compute_display_name(
                platform,
                address,
                item.get("name"),
                vendor_id_norm,
                item.get("translation_key"),
            )
            device_class = item.get("device_class")
            state_class = item.get("state_class")
            if isinstance(device_class, str) and device_class.lower() == "enum":
                state_class = None
            entities.append(
                EntityDef(
                    platform=platform,
                    name=display_name,
                    address=address,
                    vendor_id=vendor_id_norm,
                    input_type=item.get("input_type"),
                    write_type=item.get("write_type"),
                    data_type=item.get("data_type"),
                    unit_of_measurement=item.get("unit_of_measurement"),
                    device_class=device_class,
                    state_class=state_class,
                    precision=item.get("precision"),
                    unique_id=unique_id,
                    offset=item.get("offset"),
                    scale=item.get("scale"),
                    min_value=item.get("min_value"),
                )
            )
        return entities

    hub.entities.extend(_to_entity_defs("binary_sensor", spec.get("binary_sensors")))
    hub.entities.extend(_to_entity_defs("sensor", spec.get("sensors")))
    hub.entities.extend(_to_entity_defs("switch", spec.get("switches")))

    ent_reg = er.async_get(hass)

    # Drop any legacy registry entries for this config entry so we can rebuild
    # them with vendor-based slugs. This ensures previous friendly-name edits
    # do not linger across reinstalls.
    for reg_entry in list(ent_reg.entities.values()):
        if reg_entry.config_entry_id != entry.entry_id:
            continue
        try:
            ent_reg.async_remove(reg_entry.entity_id)
        except Exception:
            continue

    def _suggest_object_id(ent: EntityDef) -> str | None:
        base: str | None = ent.vendor_id or ent.unique_id
        if not base:
            return None
        base = base.lower()
        if base == "unitstatus":
            base = "qube_status_heatpump"
        if multi_device and ent.vendor_id and not base.endswith(label):
            base = f"{base}_{label}"
        return _slugify(base)

    for ent in hub.entities:
        if not ent.unique_id:
            continue
        domain = ent.platform
        slug = _suggest_object_id(ent)
        try:
            registry_entry = ent_reg.async_get_or_create(
                domain,
                DOMAIN,
                ent.unique_id,
                config_entry=entry,
                suggested_object_id=slug,
            )
        except Exception:
            continue
        if slug:
            desired_eid = f"{domain}.{slug}"
            if registry_entry.entity_id != desired_eid:
                if ent_reg.async_get(desired_eid) is None:
                    try:
                        ent_reg.async_update_entity(registry_entry.entity_id, new_entity_id=desired_eid)
                    except Exception:
                        pass

    version = "unknown"
    try:
        integration = await async_get_loaded_integration(hass, DOMAIN)
    except Exception:
        integration = None
    if not integration:
        try:
            integration = await async_get_integration(hass, DOMAIN)
        except Exception:
            integration = None
    if integration and getattr(integration, "version", None):
        version = str(integration.version)

    if multi_device:
        for other_entry in existing_entries:
            if not bool(other_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False)):
                other_updated = dict(other_entry.options)
                other_updated[CONF_SHOW_LABEL_IN_NAME] = True
                hass.config_entries.async_update_entry(other_entry, options=other_updated)

    apply_label_in_name = show_label_option or multi_device

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        if updated_entry.entry_id != entry.entry_id:
            return
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    async def _async_update_data() -> dict[str, Any]:
        await hub.async_resolve_ip()
        await hub.async_connect()
        results: dict[str, Any] = {}
        entry_store = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})
        monotonic_cache: dict[str, Any] = entry_store.setdefault("monotonic_totals", {})
        warn_count = 0
        warn_cap = 5
        for ent in hub.entities:
            try:
                value = await hub.async_read_value(ent)
            except Exception as exc:
                hub.inc_read_error()
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
            if (
                ent.state_class == "total_increasing"
                and isinstance(value, (int, float))
            ):
                last_value = monotonic_cache.get(key)
                if isinstance(last_value, (int, float)) and value < (last_value - 1e-6):
                    value = last_value
                else:
                    monotonic_cache[key] = value
            results[key] = value
        if warn_count > warn_cap:
            _LOGGER.debug("Additional read failures suppressed in this cycle")
        return results

    coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name="wp_qube_coordinator",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    alarm_group_object_id = _alarm_group_object_id(label, multi_device)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "label": label,
        "apply_label_in_name": apply_label_in_name,
        "version": version,
        "multi_device": multi_device,
        "alarm_group_object_id": alarm_group_object_id,
        "friendly_name_language": friendly_lang,
        "name_translations": name_translations,
    }

    try:
        from homeassistant.helpers import issue_registry as ir

        ir.async_delete_issue(hass, DOMAIN, "registry_migration_suggested")
    except Exception:
        pass

    for other in existing_entries:
        other_data = hass.data.get(DOMAIN, {}).get(other.entry_id)
        if other_data and not other_data.get("multi_device"):
            hass.async_create_task(hass.config_entries.async_reload(other.entry_id))

    import voluptuous as vol

    async def _async_reconfigure(call):
        from homeassistant.config_entries import SOURCE_RECONFIGURE

        data = vol.Schema({vol.Optional("entry_id"): str})(call.data)
        target_entry: ConfigEntry | None = None
        entry_id = data.get("entry_id")
        if entry_id:
            target_entry = hass.config_entries.async_get_entry(entry_id)
        else:
            entries = hass.config_entries.async_entries(DOMAIN)
            if len(entries) == 1:
                target_entry = entries[0]
        if not target_entry:
            _LOGGER.warning("reconfigure: no entry resolved; pass entry_id")
            return
        try:
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_RECONFIGURE, "entry_id": target_entry.entry_id},
                data={"entry_id": target_entry.entry_id},
            )
        except Exception as exc:
            _LOGGER.warning("reconfigure flow not available: %s", exc)

    hass.services.async_register(
        DOMAIN,
        "reconfigure",
        _async_reconfigure,
        schema=vol.Schema({vol.Optional("entry_id"): str}),
    )

    def _resolve_entry(entry_id: str | None, label_value: str | None) -> ConfigEntry | None:
        if entry_id:
            return hass.config_entries.async_get_entry(entry_id)
        if label_value:
            for cfg in hass.config_entries.async_entries(DOMAIN):
                cfg_data = hass.data.get(DOMAIN, {}).get(cfg.entry_id)
                if not cfg_data:
                    continue
                cfg_label = cfg_data.get("label") or getattr(cfg_data.get("hub"), "label", None)
                if cfg_label == label_value:
                    return cfg
        loaded_entries = [
            cfg
            for cfg in hass.config_entries.async_entries(DOMAIN)
            if hass.data.get(DOMAIN, {}).get(cfg.entry_id)
        ]
        if len(loaded_entries) == 1:
            return loaded_entries[0]
        return None

    write_register_schema = vol.Schema(
        {
            vol.Required("address"): vol.Coerce(int),
            vol.Required("value"): vol.Coerce(float),
            vol.Optional("data_type", default="uint16"): vol.In({"uint16", "int16", "float32"}),
            vol.Optional("entry_id"): str,
            vol.Optional("label"): str,
        }
    )

    async def _async_write_register(call):
        data = dict(call.data)
        data = write_register_schema(data)
        target = _resolve_entry(data.get("entry_id"), data.get("label"))
        if target is None:
            _LOGGER.error(
                "write_register: unable to resolve integration entry; specify entry_id or label"
            )
            return
        target_data = hass.data.get(DOMAIN, {}).get(target.entry_id)
        if not target_data:
            _LOGGER.error("write_register: integration entry %s is not loaded", target.entry_id)
            return
        hub_target = target_data.get("hub")
        if hub_target is None:
            _LOGGER.error("write_register: no hub available for entry %s", target.entry_id)
            return
        await hub_target.async_connect()
        data_type = str(data["data_type"]).lower()

        try:
            await hub_target.async_write_register(
                data["address"],
                data["value"],
                data_type,
            )
        except Exception as exc:
            _LOGGER.error(
                "write_register: failed to write address %s (%s)", data["address"], exc
            )
            raise
        coordinator_target = target_data.get("coordinator")
        if coordinator_target is not None:
            await coordinator_target.async_request_refresh()

    if not hass.services.has_service(DOMAIN, "write_register"):
        hass.services.async_register(
            DOMAIN,
            "write_register",
            _async_write_register,
            schema=write_register_schema,
        )

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_sync_alarm_group() -> None:
        ent_reg = er.async_get(hass)
        entity_ids: list[str] = []
        for ent in hub.entities:
            if not _is_alarm_entity(ent):
                continue
            reg_entity_id = ent_reg.async_get_entity_id(ent.platform, DOMAIN, ent.unique_id)
            if reg_entity_id:
                entity_ids.append(reg_entity_id)
        await async_setup_component(hass, "group", {})
        if not entity_ids:
            try:
                await hass.services.async_call(
                    "group",
                    "remove",
                    {"object_id": alarm_group_object_id},
                    blocking=True,
                )
            except Exception:
                _LOGGER.debug("Unable to clean up empty alarm group %s", alarm_group_object_id)
            return
        name = "Qube alarm sensors"
        if multi_device:
            name = f"Qube alarm sensors ({label})"
        service_data = {
            "object_id": alarm_group_object_id,
            "name": name,
            "icon": "mdi:alarm-light",
            "entities": sorted(set(entity_ids)),
            "all": False,
        }
        try:
            await hass.services.async_call("group", "set", service_data, blocking=True)
        except Exception as exc:  # pragma: no cover - service not available
            _LOGGER.debug("Unable to create/update alarm group: %s", exc)

    await _async_sync_alarm_group()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (hub := data.get("hub")):
        await hub.async_close()
    object_id = data.get("alarm_group_object_id") if data else None
    if object_id:
        try:
            await hass.services.async_call(
                "group",
                "remove",
                {"object_id": object_id},
                blocking=True,
            )
        except Exception:  # pragma: no cover - service not available
            _LOGGER.debug("Unable to remove alarm group %s", object_id)
    return unload_ok


def _entity_key(ent: "EntityDef") -> str:
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


def _is_alarm_entity(ent: "EntityDef") -> bool:
    if getattr(ent, "platform", None) != "binary_sensor":
        return False
    name = (getattr(ent, "name", "") or "").lower()
    if "alarm" in name:
        return True
    vendor = (getattr(ent, "vendor_id", "") or "").lower()
    return vendor.startswith("al")


def _alarm_group_object_id(label: str | None, multi_device: bool) -> str:
    base = "qube_alarm_sensors"
    if multi_device and label:
        base = f"{base}_{label}"
    return base


try:
    from .config_flow import async_get_options_flow as async_get_options_flow  # type: ignore[reimported]
except Exception:  # pragma: no cover
    async def async_get_options_flow(config_entry: ConfigEntry):
        from .config_flow import OptionsFlowHandler

        _LOGGER.debug("async_get_options_flow (lazy) for entry %s", config_entry.entry_id)
        return OptionsFlowHandler(config_entry)
