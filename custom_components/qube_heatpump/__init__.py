from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import json
import logging
from typing import Any, TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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

    raw_spec = await hass.async_add_executor_job(_load_yaml, yaml_path)
    spec = raw_spec[0] if isinstance(raw_spec, list) and raw_spec else raw_spec
    spec = dict(spec)
    spec["host"] = host
    spec["port"] = port

    unit_id = int(entry.options.get(CONF_UNIT_ID, spec.get("unit_id", 1)))

    existing_entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    multi_device = len(existing_entries) >= 1

    label = entry.options.get(CONF_LABEL)
    if not label:
        used_labels = {
            e.options.get(CONF_LABEL) for e in existing_entries if e.options.get(CONF_LABEL)
        }
        idx = 1
        while f"qube{idx}" in used_labels:
            idx += 1
        label = f"qube{idx}"
        new_options = dict(entry.options)
        new_options[CONF_LABEL] = label
        hass.config_entries.async_update_entry(entry, options=new_options)

    hub = WPQubeHub(hass, host, port, unit_id, label)

    def _compute_display_name(
        platform: str,
        address: int,
        provided: Any,
        vendor_id: str | None,
    ) -> str:
        if isinstance(provided, str):
            cleaned = provided.strip()
            if cleaned:
                return cleaned
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
            display_name = _compute_display_name(platform, address, item.get("name"), vendor_id)
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
                    device_class=item.get("device_class"),
                    state_class=item.get("state_class"),
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

    manifest = Path(__file__).parent / "manifest.json"
    version = "unknown"
    if manifest.exists():
        try:
            version_data = json.loads(manifest.read_text(encoding="utf-8"))
            maybe_version = version_data.get("version")
            if maybe_version:
                version = str(maybe_version)
        except Exception:
            version = "unknown"

    show_label_option = bool(entry.options.get(CONF_SHOW_LABEL_IN_NAME, False))
    apply_label_in_name = show_label_option or multi_device

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        if updated_entry.entry_id != entry.entry_id:
            return
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    async def _async_update_data() -> dict[str, Any]:
        await hub.async_connect()
        results: dict[str, Any] = {}
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
            results[_entity_key(ent)] = value
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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "label": label,
        "apply_label_in_name": apply_label_in_name,
        "version": version,
        "multi_device": multi_device,
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

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (hub := data.get("hub")):
        await hub.async_close()
    return unload_ok


def _entity_key(ent: "EntityDef") -> str:
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


try:
    from .config_flow import async_get_options_flow as async_get_options_flow  # type: ignore[reimported]
except Exception:  # pragma: no cover
    async def async_get_options_flow(config_entry: ConfigEntry):
        from .config_flow import OptionsFlowHandler

        _LOGGER.debug("async_get_options_flow (lazy) for entry %s", config_entry.entry_id)
        return OptionsFlowHandler(config_entry)
