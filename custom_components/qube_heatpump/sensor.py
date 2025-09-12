from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
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

    entities: list[SensorEntity] = []
    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        entities.append(WPQubeSensor(coordinator, hub.host, ent))

    async_add_entities(entities)


class WPQubeSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, host: str, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._attr_name = ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_sensor_{ent.input_type}_{ent.address}"
        self._attr_device_class = ent.device_class
        self._attr_native_unit_of_measurement = ent.unit_of_measurement
        if ent.state_class:
            self._attr_state_class = ent.state_class

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name="Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def native_value(self) -> Any:
        key = self._ent.unique_id or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        return self.coordinator.data.get(key)
