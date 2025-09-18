from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub import EntityDef


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]

    entities: list[SwitchEntity] = []
    for ent in hub.entities:
        if ent.platform != "switch":
            continue
        entities.append(WPQubeSwitch(coordinator, hub, ent))

    async_add_entities(entities)


class WPQubeSwitch(CoordinatorEntity, SwitchEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._hub = hub
        self._attr_name = ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_switch_{self._hub.host}_{self._hub.unit}_{ent.write_type}_{ent.address}"
        if getattr(ent, "vendor_id", None):
            self._attr_suggested_object_id = _slugify(ent.vendor_id)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def is_on(self) -> bool | None:
        key = self._ent.unique_id or f"switch_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)

    async def async_turn_on(self, **kwargs):
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, False)
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if getattr(self._ent, "vendor_id", None):
            registry = er.async_get(self.hass)
            current = registry.async_get(self.entity_id)
            if not current:
                return
            base_obj = _slugify(self._ent.vendor_id)
            preferred_eid = f"switch.{base_obj}"
            if current.entity_id != preferred_eid and registry.async_get(preferred_eid) is None:
                try:
                    registry.async_update_entity(self.entity_id, new_entity_id=preferred_eid)
                    return
                except Exception:
                    pass
            label = getattr(self._hub, "label", None)
            fallback_suffix = label or f"{self._hub.host}_{self._hub.unit}"
            fallback_obj = _slugify(f"{self._ent.vendor_id}_{fallback_suffix}")
            fallback_eid = f"switch.{fallback_obj}"
            if current.entity_id != fallback_eid and registry.async_get(fallback_eid) is None:
                try:
                    registry.async_update_entity(self.entity_id, new_entity_id=fallback_eid)
                except Exception:
                    pass


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()
