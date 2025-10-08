from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub import EntityDef, WPQubeHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    apply_label = bool(data.get("apply_label_in_name", False))
    multi_device = bool(data.get("multi_device", False))

    entities: list[BinarySensorEntity] = []
    for ent in hub.entities:
        if ent.platform != "binary_sensor":
            continue
        entities.append(WPQubeBinarySensor(coordinator, hub, apply_label, multi_device, ent))

    async_add_entities(entities)


async def _async_ensure_entity_id(hass: HomeAssistant, entity_id: str, desired_obj: str | None) -> None:
    if not desired_obj:
        return
    registry = er.async_get(hass)
    current = registry.async_get(entity_id)
    if not current:
        return
    desired_eid = f"{current.domain}.{desired_obj}"
    if current.entity_id == desired_eid:
        return
    if registry.async_get(desired_eid):
        return
    try:
        registry.async_update_entity(current.entity_id, new_entity_id=desired_eid)
    except Exception:
        return


class WPQubeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        show_label: bool,
        multi_device: bool,
        ent: EntityDef,
    ) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._hub = hub
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label or multi_device)
        if self._show_label:
            self._attr_name = f"{ent.name} ({self._label})"
        else:
            self._attr_name = ent.name
        if ent.unique_id:
            self._attr_unique_id = ent.unique_id
        else:
            suffix = f"{ent.input_type or 'input'}_{ent.address}".lower()
            base_uid = f"wp_qube_binary_{suffix}"
            self._attr_unique_id = f"{base_uid}_{self._label}" if multi_device else base_uid
        if getattr(ent, "vendor_id", None):
            candidate = ent.vendor_id
            if self._show_label or multi_device:
                candidate = f"{candidate}_{self._label}"
            self._attr_suggested_object_id = _slugify(candidate)

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
        key = self._ent.unique_id or f"binary_sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        desired = self._ent.vendor_id or self._attr_unique_id
        if desired and (self._show_label) and not str(desired).endswith(self._label):
            desired = f"{desired}_{self._label}"
        await _async_ensure_entity_id(self.hass, self.entity_id, _slugify(str(desired)) if desired else None)


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()
