from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    show_label = bool(data.get("show_label_in_name", False))

    entities: list[BinarySensorEntity] = []
    for ent in hub.entities:
        if ent.platform != "binary_sensor":
            continue
        entities.append(WPQubeBinarySensor(coordinator, hub.host, hub.unit, hub.label, show_label, ent))

    async_add_entities(entities)


class WPQubeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, host: str, unit: int, label: str, show_label: bool, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._unit = unit
        self._label = label
        self._attr_name = f"{ent.name} ({self._label})" if show_label else ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_binary_{self._host}_{self._unit}_{ent.input_type}_{ent.address}"
        if getattr(ent, "vendor_id", None):
            self._attr_suggested_object_id = _slugify(f"{ent.vendor_id}_{self._label}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}:{self._unit}")},
            name=(getattr(self, "_label", None) or "Qube Heatpump"),
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
        if getattr(self._ent, "vendor_id", None):
            registry = er.async_get(self.hass)
            current = registry.async_get(self.entity_id)
            if not current:
                return
            desired_obj = _slugify(f"{self._ent.vendor_id}_{self._label}")
            desired_eid = f"binary_sensor.{desired_obj}"
            if current.entity_id != desired_eid and registry.async_get(desired_eid) is None:
                try:
                    registry.async_update_entity(self.entity_id, new_entity_id=desired_eid)
                except Exception:
                    pass


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()
