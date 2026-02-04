"""Switch platform for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import EntityDef, QubeHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube switches."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    # show_label is no longer used (entity IDs are auto-generated from device name)
    show_label = False
    multi_device = data.multi_device
    version = data.version or "unknown"

    entities: list[SwitchEntity] = []
    for ent in hub.entities:
        if ent.platform != "switch":
            continue
        if ent.vendor_id in {"bms_sgready_a", "bms_sgready_b"}:
            continue
        entities.append(
            QubeSwitch(coordinator, hub, show_label, multi_device, ent, version)
        )

    async_add_entities(entities)

    # Cleanup deprecated SG Ready entities
    registry = er.async_get(hass)
    to_remove_base = ["bms_sgready_a", "bms_sgready_b"]
    for base in to_remove_base:
        uid = f"{base}_{entry.entry_id}" if multi_device else base
        entity_id = registry.async_get_entity_id("switch", DOMAIN, uid)
        if entity_id:
            registry.async_remove(entity_id)


# Switches that should appear in Controls (no entity_category) instead of Configuration
CONTROL_SWITCHES = frozenset({
    "modbus_demand",
    "tapw_timeprogram_bms_forced",
    "bms_summerwinter",
    "antilegionella_frcstart_ant",
})


class QubeSwitch(CoordinatorEntity, SwitchEntity):
    """Qube switch entity."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        show_label: bool,
        multi_device: bool,
        ent: EntityDef,
        version: str = "unknown",
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._ent = ent
        self._hub = hub
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        # Control switches go in Controls section, others in Configuration
        if ent.vendor_id not in CONTROL_SWITCHES:
            self._attr_entity_category = EntityCategory.CONFIG
        if ent.vendor_id in {"bms_sgready_a", "bms_sgready_b"}:
            self._attr_entity_registry_visible_default = False
        if ent.translation_key:
            self._attr_translation_key = ent.translation_key
            self._attr_has_entity_name = True
        else:
            self._attr_name = str(ent.name)
            self._attr_has_entity_name = True
        if ent.unique_id:
            # Scope unique_id per device in multi-device setups
            if self._multi_device:
                self._attr_unique_id = (
                    f"{self._hub.host}_{self._hub.unit}_{ent.unique_id}"
                )
            else:
                self._attr_unique_id = ent.unique_id
        else:
            suffix = f"{ent.write_type or 'coil'}_{ent.address}".lower()
            base_uid = f"qube_switch_{suffix}"
            self._attr_unique_id = (
                f"{self._hub.host}_{self._hub.unit}_{base_uid}"
                if self._multi_device
                else base_uid
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.device_name,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self._version,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        key = (
            self._ent.unique_id
            or f"switch_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        )
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, False)
        await self.coordinator.async_request_refresh()
