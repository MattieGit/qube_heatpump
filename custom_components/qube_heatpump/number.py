from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    show_label = bool(data.get("show_label_in_name", False))

    async_add_entities([QubeUnitNumber(coordinator, hub, show_label)])


class QubeUnitNumber(CoordinatorEntity, NumberEntity):
    _attr_should_poll = False
    _attr_native_min_value = 1
    _attr_native_max_value = 247
    _attr_native_step = 1
    _attr_mode = "box"

    def __init__(self, coordinator, hub, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        label = hub.label or "qube1"
        self._attr_name = f"Unit ID ({label})" if show_label else "Unit ID"
        self._attr_unique_id = f"qube_unit_id_{hub.host}_{hub.unit}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def native_value(self) -> float:
        return float(self._hub.unit)

    async def async_set_native_value(self, value: float) -> None:
        try:
            self._hub.set_unit_id(int(value))
        finally:
            await self.coordinator.async_request_refresh()

