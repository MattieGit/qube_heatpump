"""The Qube Heat Pump integration."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import logging
import re
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from .const import (
    CONF_DHW_SCHEDULE_ENABLED,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import QubeCoordinator
from .dhw_scheduler import async_setup_dhw_schedule
from .helpers import is_alarm_entity
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
    dhw_cancel_callbacks: list[Any] | None = None
    thermostat_sensor_timed_out: bool = False


type QubeConfigEntry = ConfigEntry[QubeData]

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)


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
        raise HomeAssistantError(
            "Write_register: unable to resolve integration entry; specify entry_id or label"
        )
    target_data = target.runtime_data
    if not target_data:
        raise HomeAssistantError(
            f"Write_register: integration entry {target.entry_id} is not loaded"
        )
    hub_target = target_data.hub
    if hub_target is None:
        raise HomeAssistantError(
            f"Write_register: no hub available for entry {target.entry_id}"
        )
    await hub_target.async_connect()

    try:
        await hub_target.async_write_register(
            data["address"],
            data["value"],
        )
    except ConnectionError as err:
        raise HomeAssistantError(str(err)) from err
    except Exception as err:
        _LOGGER.exception("Write_register: failed to write address %s", data["address"])
        raise HomeAssistantError(str(err)) from err
    coordinator_target = target_data.coordinator
    if coordinator_target is not None:
        await coordinator_target.async_request_refresh()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Qube Heat Pump integration's services.

    Services are registered once at component setup and survive individual
    config entries being unloaded; handlers resolve the target entry at
    call time.
    """

    async def _reconfigure_wrapper(call: ServiceCall) -> None:
        await _service_reconfigure(hass, call)

    hass.services.async_register(
        DOMAIN,
        "reconfigure",
        _reconfigure_wrapper,
        schema=vol.Schema({vol.Optional("entry_id"): str}),
    )

    async def _write_register_wrapper(call: ServiceCall) -> None:
        await _service_write_register(hass, call)

    hass.services.async_register(
        DOMAIN,
        "write_register",
        _write_register_wrapper,
        schema=WRITE_REGISTER_SCHEMA,
    )

    return True


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

    await hub.async_resolve_ip()

    # Load entities from the python-qube-heatpump library
    hub.load_library_entities()

    # Get firmware version from the device (library v1.6.0+)
    version: str | None = None
    try:
        await hub.async_connect()
        version = await hub.async_get_software_version()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not read firmware version during setup")
    if not version:
        version = "unknown"

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

    # Note: We no longer reload existing entries when adding new ones.
    # Unique IDs are always scoped with host_unit prefix, so they remain
    # stable regardless of how many devices are configured.

    # Restore the monotonic cache from disk so that float32 jitter
    # after restart doesn't produce false decreases in total_increasing sensors.
    await coordinator.async_load_monotonic_cache()

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up DHW schedule if enabled
    if entry.options.get(CONF_DHW_SCHEDULE_ENABLED):
        dhw_callbacks = await async_setup_dhw_schedule(hass, entry, hub, coordinator)
        entry.runtime_data.dhw_cancel_callbacks = dhw_callbacks

    # Alarm group sync (label and alarm_group_id already computed above)
    # Construct entity IDs directly from vendor_id to ensure consistency
    # (registry lookup can return stale entity IDs after reinstall)
    entity_ids: list[str] = []
    for ent in hub.entities:
        if not is_alarm_entity(ent):
            continue
        vendor_id = getattr(ent, "vendor_id", None)
        if vendor_id:
            entity_ids.append(f"binary_sensor.{label}_{vendor_id}")
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

    # Cancel DHW schedule callbacks
    with contextlib.suppress(AttributeError):
        if callbacks := entry.runtime_data.dhw_cancel_callbacks:
            for cancel in callbacks:
                cancel()

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
