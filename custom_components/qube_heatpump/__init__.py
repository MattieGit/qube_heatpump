"""The Qube Heat Pump integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.util import slugify

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import QubeCoordinator, connection_issue_id, monotonic_store
from .dhw_scheduler import DhwScheduleState, async_setup_dhw_schedule
from .helpers import is_alarm_entity
from .hub import QubeHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType


@dataclass
class QubeData:
    """Runtime data for Qube Heat Pump."""

    hub: QubeHub
    coordinator: QubeCoordinator
    device_name: str
    version: str
    multi_device: bool
    alarm_group_object_id: str | None = None
    dhw_schedule: DhwScheduleState | None = None
    thermostat_sensor_timed_out: bool = False


type QubeConfigEntry = ConfigEntry[QubeData]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RECONFIGURE_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})

WRITE_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Required("address"): vol.Coerce(int),
        vol.Required("value"): vol.Coerce(float),
        vol.Optional("entry_id"): str,
        vol.Optional("label"): str,
    }
)


def _alarm_group_object_id(label: str) -> str:
    """Generate the alarm group object_id for a hub label."""
    slug = slugify(label)
    return f"qube_alarms_{slug}" if slug else "qube_alarms"


def _loaded_entries(hass: HomeAssistant) -> list[QubeConfigEntry]:
    """Return the config entries that are currently set up."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def _resolve_entry(
    hass: HomeAssistant, entry_id: str | None, label: str | None
) -> ConfigEntry | None:
    """Resolve the target config entry of a service call.

    An explicit entry_id wins. A label must match a loaded hub's label
    exactly; a label that matches nothing resolves to None rather than
    silently falling back to another entry. Without either, the single
    loaded entry is used.
    """
    if entry_id:
        return hass.config_entries.async_get_entry(entry_id)
    loaded = _loaded_entries(hass)
    if label:
        return next(
            (entry for entry in loaded if entry.runtime_data.hub.label == label),
            None,
        )
    if len(loaded) == 1:
        return loaded[0]
    return None


async def _service_reconfigure(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the reconfigure service by starting the reconfigure flow."""
    target_entry: ConfigEntry | None = None
    if entry_id := call.data.get("entry_id"):
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
        )
    except HomeAssistantError as exc:
        _LOGGER.warning("Reconfigure flow not available: %s", exc)


async def _service_write_register(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the write_register service."""
    address: int = call.data["address"]
    target = _resolve_entry(hass, call.data.get("entry_id"), call.data.get("label"))
    if target is None:
        raise HomeAssistantError(
            "Write_register: unable to resolve integration entry; specify entry_id or label"
        )
    if target.state is not ConfigEntryState.LOADED:
        raise HomeAssistantError(
            f"Write_register: integration entry {target.entry_id} is not loaded"
        )
    data: QubeData = target.runtime_data
    try:
        await data.hub.async_connect()
        await data.hub.async_write_register(address, call.data["value"])
    except ValueError as err:
        # Unknown address or an invalid coil value: a caller error
        raise HomeAssistantError(str(err)) from err
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_register_failed",
            translation_placeholders={"address": str(address)},
        ) from err
    await data.coordinator.async_request_refresh()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Qube Heat Pump integration's services.

    Services are registered once at component setup and survive individual
    config entries being unloaded; handlers resolve the target entry at
    call time.
    """

    async def _reconfigure_wrapper(call: ServiceCall) -> None:
        await _service_reconfigure(hass, call)

    hass.services.async_register(
        DOMAIN, "reconfigure", _reconfigure_wrapper, schema=RECONFIGURE_SCHEMA
    )

    async def _write_register_wrapper(call: ServiceCall) -> None:
        await _service_write_register(hass, call)

    hass.services.async_register(
        DOMAIN, "write_register", _write_register_wrapper, schema=WRITE_REGISTER_SCHEMA
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Set up Qube Heat Pump from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    # Legacy: the unit id was once configurable; it is fixed at 1 today.
    unit_id = int(entry.options.get(CONF_UNIT_ID, entry.data.get(CONF_UNIT_ID, 1)))

    other_entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    multi_device = bool(other_entries)

    # Entries created before CONF_NAME existed get a numbered default name.
    # The name drives the hub label and therefore every entity_id, so it is
    # persisted on first load and never derived from the title afterwards.
    device_name = entry.data.get(CONF_NAME)
    if not device_name:
        device_name = f"qube {len(other_entries) + 1}"
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_NAME: device_name}, title=device_name
        )

    hub = QubeHub(host, port, unit_id, device_name)
    await hub.async_resolve_ip()
    hub.load_library_entities()

    coordinator = QubeCoordinator(hass, hub, entry)
    alarm_group_id = _alarm_group_object_id(hub.label)

    entry.runtime_data = QubeData(
        hub=hub,
        coordinator=coordinator,
        device_name=device_name,
        version="unknown",
        multi_device=multi_device,
        alarm_group_object_id=alarm_group_id,
        # Built before the platforms load so the schedule entities can render
        # a consistent state even when the schedule is disabled.
        dhw_schedule=DhwScheduleState.from_options(entry.options),
    )

    # Restore the monotonic cache from disk so that float32 jitter
    # after restart doesn't produce false decreases in total_increasing sensors.
    await coordinator.async_load_monotonic_cache()

    # Connects, reads the firmware version and polls once; raises
    # ConfigEntryNotReady when the device is unreachable.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data.version = coordinator.sw_version or "unknown"

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the DHW schedule callbacks (no-op when disabled)
    for cancel in await async_setup_dhw_schedule(
        hass, entry, hub, coordinator, entry.runtime_data.dhw_schedule
    ):
        entry.async_on_unload(cancel)

    # Alarm group: entity IDs are constructed from vendor_id so they match
    # the binary sensors even when the registry holds stale IDs.
    label = hub.label
    entity_ids = sorted(
        {
            f"binary_sensor.{label}_{ent.vendor_id}"
            for ent in hub.entities
            if ent.vendor_id and is_alarm_entity(ent)
        }
    )
    await hass.services.async_call(
        "group",
        "set",
        {
            "object_id": alarm_group_id,
            "name": f"Qube alarm sensors ({label})"
            if multi_device
            else "Qube alarm sensors",
            "icon": "mdi:alarm-light",
            "entities": entity_ids,
            "all": False,
        },
        blocking=True,
    )

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options or data change."""
    # Skip reloads triggered while the entry is still being set up
    if entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = entry.runtime_data
        await data.hub.async_close()
        await hass.services.async_call(
            "group",
            "remove",
            {"object_id": data.alarm_group_object_id},
            blocking=True,
        )
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the per-entry state left behind on disk and in the issue registry."""
    await monotonic_store(hass, entry.entry_id).async_remove()
    ir.async_delete_issue(hass, DOMAIN, connection_issue_id(entry.entry_id))
