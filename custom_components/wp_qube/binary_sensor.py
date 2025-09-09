from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub import EntityDef


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]

    entities: list[BinarySensorEntity] = []
    for ent in hub.entities:
        if ent.platform != "binary_sensor":
            continue
        entities.append(WPQubeBinarySensor(coordinator, hub.host, ent))

    async_add_entities(entities)


class WPQubeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, host: str, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._attr_name = ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_binary_{ent.input_type}_{ent.address}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name="Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def is_on(self) -> bool | None:
        key = self._ent.unique_id or f"binary_sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)
