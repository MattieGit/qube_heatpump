"""The Qube Heat Pump integration."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.loader import async_get_integration, async_get_loaded_integration
from homeassistant.setup import async_setup_component

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import QubeCoordinator
from .hub import QubeHub


@dataclass
class QubeData:
    """Runtime data for Qube Heat Pump."""

    hub: QubeHub
    coordinator: QubeCoordinator
    device_name: str
    version: str
    multi_device: bool
    alarm_group_object_id: str | None = None
    tariff_tracker: Any | None = None
    thermic_tariff_tracker: Any | None = None
    daily_tariff_tracker: Any | None = None
    daily_thermic_tariff_tracker: Any | None = None


type QubeConfigEntry = ConfigEntry[QubeData]

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)


def _is_alarm_entity(ent: Any) -> bool:
    """Check if an entity is an alarm entity."""
    if ent.platform != "binary_sensor":
        return False
    vendor_id = (ent.vendor_id or "").lower()
    name_lower = (ent.name or "").lower()
    return (
        "alarm" in vendor_id
        or vendor_id.startswith("al_")
        or "alarm" in name_lower
        or name_lower.startswith("al ")
    )


def _alarm_group_object_id(label: str) -> str:
    """Generate the alarm group object_id."""
    # Slugify the label
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"qube_alarms_{slug}" if slug else "qube_alarms"


def _resolve_entry(
    hass: HomeAssistant, entry_id: str | None, label_value: str | None
) -> ConfigEntry | None:
    """Resolve a config entry from ID or label."""
    if entry_id:
        return hass.config_entries.async_get_entry(entry_id)
    if label_value:
        for cfg in hass.config_entries.async_entries(DOMAIN):
            if not isinstance(cfg, ConfigEntry):
                continue
            # We can't strictly type check runtime_data here easily without casting,
            # but we know it's QubeData if loaded.
            try:
                data = cfg.runtime_data
                # runtime_data might not be loaded if entry is not setup
                if (
                    getattr(data, "label", None) == label_value
                    or getattr(data.hub, "label", None) == label_value
                ):
                    return cfg
            except AttributeError:
                continue
    loaded_entries = [
        cfg
        for cfg in hass.config_entries.async_entries(DOMAIN)
        if getattr(cfg, "runtime_data", None)
    ]
    if len(loaded_entries) == 1:
        return loaded_entries[0]
    return None


async def _service_reconfigure(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the reconfigure service."""
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
        _LOGGER.warning("Reconfigure: no entry resolved; pass entry_id")
        return
    try:
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": SOURCE_RECONFIGURE,
                "entry_id": target_entry.entry_id,
            },
            data={"entry_id": target_entry.entry_id},
        )
    except HomeAssistantError as exc:
        _LOGGER.warning("Reconfigure flow not available: %s", exc)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        _LOGGER.warning("Unexpected error in reconfigure flow: %s", exc)


WRITE_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Required("address"): vol.Coerce(int),
        vol.Required("value"): vol.Coerce(float),
        vol.Optional("data_type", default="uint16"): vol.In(
            {"uint16", "int16", "float32"}
        ),
        vol.Optional("entry_id"): str,
        vol.Optional("label"): str,
    }
)


async def _service_write_register(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the write_register service."""
    data = dict(call.data)
    data = WRITE_REGISTER_SCHEMA(data)
    target = _resolve_entry(hass, data.get("entry_id"), data.get("label"))
    if target is None:
        _LOGGER.error(
            "Write_register: unable to resolve integration entry; specify entry_id or label"
        )
        return
    target_data = target.runtime_data
    if not target_data:
        _LOGGER.error(
            "Write_register: integration entry %s is not loaded", target.entry_id
        )
        return
    hub_target = target_data.hub
    if hub_target is None:
        _LOGGER.error("Write_register: no hub available for entry %s", target.entry_id)
        return
    await hub_target.async_connect()
    data_type = str(data["data_type"]).lower()

    try:
        await hub_target.async_write_register(
            data["address"],
            data["value"],
            data_type,
        )
    except ConnectionError as err:
        _LOGGER.error("Write_register: %s", err)
        raise HomeAssistantError(str(err)) from err
    except Exception:
        _LOGGER.exception("Write_register: failed to write address %s", data["address"])
        raise
    coordinator_target = target_data.coordinator
    if coordinator_target is not None:
        await coordinator_target.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Set up Qube Heat Pump from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    options = dict(entry.options)

    unit_id = int(options.get(CONF_UNIT_ID, 1))

    existing_entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    multi_device = len(existing_entries) >= 1

    # Get device name from entry data or fall back to title
    device_name = entry.data.get(CONF_NAME) or entry.title

    # Migration: update old entries without CONF_NAME
    if CONF_NAME not in entry.data:
        # Generate a name based on existing entry count
        device_number = len(existing_entries) + 1
        device_name = f"qube {device_number}"
        new_data = dict(entry.data)
        new_data[CONF_NAME] = device_name
        hass.config_entries.async_update_entry(entry, data=new_data, title=device_name)

    hub = QubeHub(hass, host, port, entry.entry_id, unit_id, device_name)

    # Load fallback translations (manual resolution to avoid device prefix)
    translations_path = Path(__file__).parent / "translations" / "en.json"
    if translations_path.exists():

        def _load_translations() -> dict[str, Any]:
            with translations_path.open("r", encoding="utf-8") as f:
                return cast("dict[str, Any]", json.load(f))

        with contextlib.suppress(OSError, ValueError):
            translations = await hass.async_add_executor_job(_load_translations)
            hub.set_translations(translations)

    await hub.async_resolve_ip()

    # Load entities from the python-qube-heatpump library
    hub.load_library_entities()

    version = "unknown"
    with contextlib.suppress(Exception):
        integration = async_get_loaded_integration(hass, DOMAIN)
        if not integration:
            integration = await async_get_integration(hass, DOMAIN)
        if integration and getattr(integration, "version", None):
            version = str(integration.version)

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        """Handle options update."""
        if updated_entry.entry_id != entry.entry_id:
            return
        # Avoid reloading if we are currently in the process of setting up
        if updated_entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    coordinator = QubeCoordinator(hass, hub, entry)

    # Prepare alarm group object ID for later use
    label = hub.label
    alarm_group_id = _alarm_group_object_id(label)

    entry.runtime_data = QubeData(
        hub=hub,
        coordinator=coordinator,
        device_name=device_name,
        version=version,
        multi_device=multi_device,
        alarm_group_object_id=alarm_group_id,
    )

    with contextlib.suppress(Exception):
        ir.async_delete_issue(hass, DOMAIN, "registry_migration_suggested")

    for other in existing_entries:
        if (
            other.state is ConfigEntryState.LOADED
            and hasattr(other, "runtime_data")
            and not other.runtime_data.multi_device
        ):
            hass.async_create_task(hass.config_entries.async_reload(other.entry_id))

    if not hass.services.has_service(DOMAIN, "reconfigure"):

        async def _reconfigure_wrapper(call: ServiceCall) -> None:
            await _service_reconfigure(hass, call)

        hass.services.async_register(
            DOMAIN,
            "reconfigure",
            _reconfigure_wrapper,
            schema=vol.Schema({vol.Optional("entry_id"): str}),
        )

    if not hass.services.has_service(DOMAIN, "write_register"):

        async def _write_register_wrapper(call: ServiceCall) -> None:
            await _service_write_register(hass, call)

        hass.services.async_register(
            DOMAIN,
            "write_register",
            _write_register_wrapper,
            schema=WRITE_REGISTER_SCHEMA,
        )

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Alarm group sync (label and alarm_group_id already computed above)
    ant_reg = er.async_get(hass)
    entity_ids: list[str] = []
    for ent in hub.entities:
        if not _is_alarm_entity(ent):
            continue
        if not ent.unique_id:
            continue
        reg_entity_id = ant_reg.async_get_entity_id(ent.platform, DOMAIN, ent.unique_id)
        if reg_entity_id:
            entity_ids.append(reg_entity_id)
    await async_setup_component(hass, "group", {})
    if not entity_ids:
        with contextlib.suppress(Exception):
            await hass.services.async_call(
                "group",
                "remove",
                {"object_id": alarm_group_id},
                blocking=True,
            )
    else:
        name = "Qube alarm sensors"
        if multi_device:
            name = f"Qube alarm sensors ({label})"
        service_data = {
            "object_id": alarm_group_id,
            "name": name,
            "icon": "mdi:alarm-light",
            "entities": sorted(set(entity_ids)),
            "all": False,
        }
        with contextlib.suppress(Exception):
            await hass.services.async_call("group", "set", service_data, blocking=True)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Use contextlib.suppress to safely handle cleanup even if setup failed
    with contextlib.suppress(AttributeError):
        if hub := entry.runtime_data.hub:
            await hub.async_close()

    with contextlib.suppress(AttributeError):
        if object_id := entry.runtime_data.alarm_group_object_id:
            with contextlib.suppress(Exception):
                await hass.services.async_call(
                    "group",
                    "remove",
                    {"object_id": object_id},
                    blocking=True,
                )

    return bool(unload_ok)
