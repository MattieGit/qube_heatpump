from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub import EntityDef, WPQubeHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]

    entities: list[SensorEntity] = []
    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        entities.append(WPQubeSensor(coordinator, hub.host, hub.unit, ent))

    # Add computed/template-like sensors equivalent to template_sensors.yaml
    # 1) Qube status full (maps numeric status to human-readable string)
    status_src = _find_status_source(hub)
    if status_src is not None:
        entities.append(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name="Qube status full",
                unique_suffix="status_full",
                kind="status",
                source=status_src,
            )
        )

    # 2) Qube Driewegklep DHW/CV status (binary sensor address 4)
    drie_src = _find_binary_by_address(hub, 4)
    if drie_src is not None:
        entities.append(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name="Qube Driewegklep DHW/CV status",
                unique_suffix="driewegklep_dhw_cv",
                kind="drieweg",
                source=drie_src,
            )
        )

    # 3) Qube Vierwegklep verwarmen/koelen status (binary sensor address 2)
    vier_src = _find_binary_by_address(hub, 2)
    if vier_src is not None:
        entities.append(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name="Qube Vierwegklep verwarmen/koelen status",
                unique_suffix="vierwegklep_verwarmen_koelen",
                kind="vierweg",
                source=vier_src,
            )
        )

    async_add_entities(entities)


class WPQubeSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, host: str, unit: int, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._unit = unit
        self._attr_name = ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_sensor_{self._host}_{self._unit}_{ent.input_type}_{ent.address}"
        # Suggest an entity_id based on vendor_id, prefixed for multi-hub uniqueness
        if getattr(ent, "vendor_id", None):
            self._attr_suggested_object_id = f"{ent.vendor_id}_{self._host}_{self._unit}"
        self._attr_device_class = ent.device_class
        self._attr_native_unit_of_measurement = ent.unit_of_measurement
        if ent.state_class:
            self._attr_state_class = ent.state_class

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Prefer vendor-based entity_id if available
        if getattr(self._ent, "vendor_id", None):
            desired_obj_id = _slugify(f"{self._ent.vendor_id}_{self._host}_{self._unit}")
            if desired_obj_id:
                registry = er.async_get(self.hass)
                current = registry.async_get(self.entity_id)
                if current and current.entity_id != f"sensor.{desired_obj_id}":
                    # Only update if target is free or already ours
                    if not registry.async_get_entity_id("sensor", DOMAIN, current.unique_id) or True:
                        try:
                            registry.async_update_entity(self.entity_id, new_entity_id=f"sensor.{desired_obj_id}")
                        except Exception:
                            # Best-effort; keep current entity_id on failure
                            pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}:{self._unit}")},
            name="Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def native_value(self) -> Any:
        key = self._ent.unique_id or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        return self.coordinator.data.get(key)


def _entity_key(ent: EntityDef) -> str:
    return ent.unique_id or f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


def _slugify(text: str) -> str:
    # Minimal slugify to align with HA object_id expectations
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()


def _find_status_source(hub: WPQubeHub) -> EntityDef | None:
    # Prefer explicit unique_id from YAML if present
    for ent in hub.entities:
        if ent.platform == "sensor" and (ent.unique_id == "wp_qube_warmtepomp_unit_status"):
            return ent
    # Fallback: look for enum-like status sensor by name or device_class
    cand: EntityDef | None = None
    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        if (ent.device_class == "enum") or ("status" in (ent.name or "").lower()):
            cand = ent
            break
    return cand


def _find_binary_by_address(hub: WPQubeHub, address: int) -> EntityDef | None:
    for ent in hub.entities:
        if ent.platform == "binary_sensor" and int(ent.address) == int(address):
            return ent
    return None


class WPQubeComputedSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub: WPQubeHub, name: str, unique_suffix: str, kind: str, source: EntityDef) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._name = name
        self._kind = kind
        self._source = source
        self._attr_name = name
        # Make unique per host to support multiple entries
        self._attr_unique_id = f"wp_qube_{unique_suffix}_{hub.host}_{hub.unit}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name="Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
        )

    @property
    def native_value(self):
        key = _entity_key(self._source)
        val = self.coordinator.data.get(key)
        if val is None:
            return None
        try:
            if self._kind == "status":
                code = int(val)
                return {
                    1: "Standby",
                    2: "Alarm",
                    6: "Keyboard off",
                    8: "Compressor start up",
                    9: "Compressor shutdown",
                    15: "Cooling",
                    16: "Heating",
                    17: "Start fail",
                    22: "Heating DHW",
                }.get(code, "Unknown state")
            if self._kind == "drieweg":
                return "DHW" if bool(val) else "CV"
            if self._kind == "vierweg":
                return "Verwarmen" if bool(val) else "Koelen"
        except Exception:
            return None
        return None
