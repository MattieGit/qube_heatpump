from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_loaded_integration, async_get_integration

from .const import DOMAIN
from .hub import EntityDef, WPQubeHub


VENDOR_SLUG_OVERRIDES = {
    "unitstatus": "qube_status_heatpump",
}

HIDDEN_VENDOR_IDS = {
    "unitstatus",
    "dout_threewayvlv_val",
    "dout_fourwayvlv_val",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    version = data.get("version", "unknown")
    apply_label = bool(data.get("apply_label_in_name", False))
    multi_device = bool(data.get("multi_device", False))

    entities: list[SensorEntity] = []
    # Add a diagnostic Qube info sensor per device
    entities.append(QubeInfoSensor(coordinator, hub, apply_label, multi_device, version))

    # Add key diagnostic metrics as separate sensors so users can mark them as
    # Preferred on the device page for quick visibility.
    entities.extend(
        [
            QubeMetricSensor(coordinator, hub, apply_label, multi_device, version, kind="errors_connect"),
            QubeMetricSensor(coordinator, hub, apply_label, multi_device, version, kind="errors_read"),
            QubeMetricSensor(coordinator, hub, apply_label, multi_device, version, kind="count_sensors"),
            QubeMetricSensor(
                coordinator, hub, apply_label, multi_device, version, kind="count_binary_sensors"
            ),
            QubeMetricSensor(coordinator, hub, apply_label, multi_device, version, kind="count_switches"),
        ]
    )

    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        entities.append(
            WPQubeSensor(
                coordinator,
                hub.host,
                hub.unit,
                hub.label,
                apply_label,
                multi_device,
                version,
                ent,
            )
        )

    # Add computed/template-like sensors equivalent to template_sensors.yaml
    # 1) Qube status full (maps numeric status to human-readable string)
    status_src = _find_status_source(hub)
    if status_src is not None:
        entities.append(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name="Status warmtepomp",
                unique_suffix="status_full",
                kind="status",
                source=status_src,
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
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
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
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
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
            )
        )

    async_add_entities(entities)


async def _async_ensure_entity_id(hass: HomeAssistant, entity_id: str, desired_obj: str | None) -> None:
    """Ensure the entity_id aligns with the desired object id when possible."""

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


class WPQubeSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        host: str,
        unit: int,
        label: str,
        show_label: bool,
        multi_device: bool,
        version: str,
        ent: EntityDef,
    ) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._unit = unit
        self._label = label
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        if self._show_label or self._multi_device:
            self._attr_name = f"{ent.name} ({_format_label(self._label)})"
        else:
            self._attr_name = ent.name
        if ent.unique_id:
            self._attr_unique_id = ent.unique_id
        else:
            suffix_parts = []
            if ent.input_type:
                suffix_parts.append(str(ent.input_type))
            if ent.write_type and not suffix_parts:
                suffix_parts.append(str(ent.write_type))
            suffix_parts.append(str(ent.address))
            suffix = "_".join(str(part) for part in suffix_parts if part)
            unique_base = f"wp_qube_{ent.platform}_{suffix}".lower()
            if self._multi_device:
                unique_base = f"{unique_base}_{self._label}"
            self._attr_unique_id = unique_base
        vendor_id = getattr(ent, "vendor_id", None)
        if vendor_id in HIDDEN_VENDOR_IDS:
            self._attr_entity_registry_visible_default = False
            self._attr_entity_registry_enabled_default = False
        if vendor_id:
            vendor_slug = VENDOR_SLUG_OVERRIDES.get(ent.vendor_id, ent.vendor_id)
            desired = vendor_slug
            if self._show_label or self._multi_device:
                desired = f"{desired}_{self._label}"
            self._attr_suggested_object_id = _slugify(desired)
        self._attr_device_class = ent.device_class
        self._attr_native_unit_of_measurement = ent.unit_of_measurement
        if ent.state_class:
            self._attr_state_class = ent.state_class
        # Hint UI display precision to avoid decimals for precision 0 (e.g., kWh totals)
        if getattr(ent, "precision", None) is not None:
            try:
                self._attr_suggested_display_precision = int(ent.precision)  # type: ignore[attr-defined]
            except Exception:
                pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}:{self._unit}")},
            name=(self._label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> Any:
        key = self._ent.unique_id or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        return self.coordinator.data.get(key)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        vendor_slug = VENDOR_SLUG_OVERRIDES.get(self._ent.vendor_id, self._ent.vendor_id)
        desired = vendor_slug or self._attr_unique_id
        if desired and (self._show_label or self._multi_device) and not str(desired).endswith(self._label):
            desired = f"{desired}_{self._label}"
        desired_slug = _slugify(str(desired)) if desired else None
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_slug)

class QubeInfoSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        hub,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label or multi_device)
        self._version = str(version) if version else "unknown"
        label = hub.label or "qube1"
        disp = _format_label(label) if self._show_label else None
        self._attr_name = f"Qube info ({disp})" if disp else "Qube info"
        self._attr_unique_id = (
            f"qube_info_sensor_{label}" if self._multi_device else "qube_info_sensor"
        )
        self._state = "ok"
        if self._show_label or self._multi_device:
            self._attr_suggested_object_id = _slugify(f"qube_info_{label}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        hub = self._hub
        sensors = sum(1 for e in hub.entities if e.platform == "sensor")
        bsens = sum(1 for e in hub.entities if e.platform == "binary_sensor")
        switches = sum(1 for e in hub.entities if e.platform == "switch")
        return {
            "version": self._version,
            "label": hub.label,
            "host": hub.host,
            "ip_address": hub.resolved_ip,
            "unit_id": hub.unit,
            "errors_connect": hub.err_connect,
            "errors_read": hub.err_read,
            "count_sensors": sensors,
            "count_binary_sensors": bsens,
            "count_switches": switches,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_refresh_integration_version()
        desired_obj = "qube_info"
        if self._show_label or self._multi_device:
            desired_obj = _slugify(f"qube_info_{self._hub.label}")
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_obj)

    async def _async_refresh_integration_version(self) -> None:
        try:
            integ = await async_get_loaded_integration(self.hass, DOMAIN)
        except Exception:
            integ = None
        if not integ:
            try:
                integ = await async_get_integration(self.hass, DOMAIN)
            except Exception:
                integ = None
        try:
            if integ and getattr(integ, "version", None):
                new_version = str(integ.version)
                if new_version and new_version != self._version:
                    self._version = new_version
                    self.async_write_ha_state()
        except Exception:
            pass


class QubeMetricSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        show_label: bool,
        multi_device: bool,
        version: str,
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._kind = kind
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label or multi_device)
        self._version = version
        label = hub.label or "qube1"
        name = {
            "errors_connect": "Qube connect errors",
            "errors_read": "Qube read errors",
            "count_sensors": "Qube sensor count",
            "count_binary_sensors": "Qube binary sensor count",
            "count_switches": "Qube switch count",
        }.get(kind, kind)
        disp = _format_label(label) if self._show_label else None
        self._attr_name = f"{name} ({disp})" if disp else name
        base_uid = f"qube_metric_{kind}"
        self._attr_unique_id = f"{base_uid}_{label}" if self._multi_device else base_uid
        if self._show_label or self._multi_device:
            self._attr_suggested_object_id = _slugify(f"{base_uid}_{label}")
        # These are plain numeric counters; mark as measurement for charts.
        try:
            from homeassistant.components.sensor import SensorStateClass

            self._attr_state_class = SensorStateClass.MEASUREMENT
        except Exception:
            pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self):
        hub = self._hub
        if self._kind == "errors_connect":
            return getattr(hub, "err_connect", None)
        if self._kind == "errors_read":
            return getattr(hub, "err_read", None)
        if self._kind == "count_sensors":
            return sum(1 for e in hub.entities if e.platform == "sensor")
        if self._kind == "count_binary_sensors":
            return sum(1 for e in hub.entities if e.platform == "binary_sensor")
        if self._kind == "count_switches":
            return sum(1 for e in hub.entities if e.platform == "switch")
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        suffix = f"_{self._hub.label}" if (self._show_label or self._multi_device) else ""
        desired_obj = _slugify(f"qube_metric_{self._kind}{suffix}")
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_obj)


def _entity_key(ent: EntityDef) -> str:
    return ent.unique_id or f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


def _slugify(text: str) -> str:
    # Minimal slugify to align with HA object_id expectations
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()


def _format_label(label: str) -> str:
    """Insert a space before trailing digits in label (e.g., qube1 -> qube 1)."""
    try:
        import re

        return re.sub(r"^(.*?)(\d+)$", r"\1 \2", str(label))
    except Exception:
        return label


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

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        name: str,
        unique_suffix: str,
        kind: str,
        source: EntityDef,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._name = name
        self._kind = kind
        self._source = source
        self._version = version
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label or multi_device)
        self._label = hub.label or "qube1"
        self._object_base = _slugify(name)
        disp = _format_label(self._label) if self._show_label else None
        self._attr_name = f"{name} ({disp})" if disp else name
        base_unique = f"wp_qube_{unique_suffix}"
        self._attr_unique_id = (
            f"{base_unique}_{self._label}" if self._multi_device else base_unique
        )
        if self._show_label or self._multi_device:
            self._attr_suggested_object_id = f"{self._object_base}_{self._label}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
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
                if code in (1, 14, 18):
                    return "Standby"
                return {
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        desired = self._attr_unique_id or self._object_base
        await _async_ensure_entity_id(self.hass, self.entity_id, _slugify(str(desired)))
