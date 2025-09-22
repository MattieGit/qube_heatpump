from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_loaded_integration, async_get_integration
from pathlib import Path
import json

from .const import DOMAIN
from .hub import EntityDef, WPQubeHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    show_label = bool(data.get("show_label_combined", False))
    # For diagnostics, auto-show label when multiple devices exist
    show_label_diag = bool(data.get("force_label_in_diag", False)) or show_label

    entities: list[SensorEntity] = []
    # Add a diagnostic Qube info sensor per device
    entities.append(QubeInfoSensor(coordinator, hub, show_label_diag))

    # Add key diagnostic metrics as separate sensors so users can mark them as
    # Preferred on the device page for quick visibility.
    entities.extend(
        [
            QubeMetricSensor(coordinator, hub, show_label_diag, kind="errors_connect"),
            QubeMetricSensor(coordinator, hub, show_label_diag, kind="errors_read"),
            QubeMetricSensor(coordinator, hub, show_label_diag, kind="count_sensors"),
            QubeMetricSensor(
                coordinator, hub, show_label_diag, kind="count_binary_sensors"
            ),
            QubeMetricSensor(coordinator, hub, show_label_diag, kind="count_switches"),
        ]
    )

    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        entities.append(WPQubeSensor(coordinator, hub.host, hub.unit, hub.label, show_label, ent))

    # Add computed/template-like sensors equivalent to template_sensors.yaml
    # 1) Qube status full (maps numeric status to human-readable string)
    status_src = _find_status_source(hub)
    if status_src is not None:
        entities.append(WPQubeComputedSensor(coordinator, hub, name="Qube status full", unique_suffix="status_full", kind="status", source=status_src))

    # 2) Qube Driewegklep DHW/CV status (binary sensor address 4)
    drie_src = _find_binary_by_address(hub, 4)
    if drie_src is not None:
        entities.append(WPQubeComputedSensor(coordinator, hub, name="Qube Driewegklep DHW/CV status", unique_suffix="driewegklep_dhw_cv", kind="drieweg", source=drie_src))

    # 3) Qube Vierwegklep verwarmen/koelen status (binary sensor address 2)
    vier_src = _find_binary_by_address(hub, 2)
    if vier_src is not None:
        entities.append(WPQubeComputedSensor(coordinator, hub, name="Qube Vierwegklep verwarmen/koelen status", unique_suffix="vierwegklep_verwarmen_koelen", kind="vierweg", source=vier_src))

    async_add_entities(entities)


def _resolve_integration_version() -> str:
    """Resolve integration version from manifest.

    Keep simple and synchronous: read bundled manifest.json and return its version.
    """
    try:
        manifest = Path(__file__).resolve().parent / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            vers = data.get("version")
            if vers:
                return str(vers)
    except Exception:
        pass
    return "unknown"


class WPQubeSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, host: str, unit: int, label: str, show_label: bool, ent: EntityDef) -> None:
        super().__init__(coordinator)
        self._ent = ent
        self._host = host
        self._unit = unit
        self._label = label
        self._attr_name = f"{ent.name} ({self._label})" if show_label else ent.name
        self._attr_unique_id = ent.unique_id or f"wp_qube_sensor_{self._label}_{ent.input_type}_{ent.address}"
        # Suggest vendor-only entity_id; conflict fallback handled in async_added_to_hass
        if getattr(ent, "vendor_id", None):
            self._attr_suggested_object_id = _slugify(f"{ent.vendor_id}_{self._label}")
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Always prefer vendor+label entity_id
        if getattr(self._ent, "vendor_id", None):
            registry = er.async_get(self.hass)
            current = registry.async_get(self.entity_id)
            if not current:
                return
            desired_obj = _slugify(f"{self._ent.vendor_id}_{self._label}")
            desired_eid = f"sensor.{desired_obj}"
            if current.entity_id != desired_eid and registry.async_get(desired_eid) is None:
                try:
                    registry.async_update_entity(self.entity_id, new_entity_id=desired_eid)
                except Exception:
                    pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}:{self._unit}")},
            name=(self._label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=_resolve_integration_version(),
        )

    @property
    def native_value(self) -> Any:
        key = self._ent.unique_id or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        return self.coordinator.data.get(key)


class QubeInfoSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, hub, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        label = hub.label or "qube1"
        disp = _format_label(label) if show_label else None
        self._attr_name = f"Qube info ({disp})" if show_label else "Qube info"
        self._attr_unique_id = f"qube_info_sensor_{label}"
        self._state = "ok"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=_resolve_integration_version(),
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
        version = "unknown"
        try:
            integ = self.hass.async_add_job(async_get_loaded_integration, self.hass, DOMAIN)
        except Exception:
            integ = None
        if hasattr(integ, "result"):
            integ = integ.result()
        if not integ:
            try:
                integ = self.hass.async_add_job(async_get_integration, self.hass, DOMAIN)
            except Exception:
                integ = None
            if hasattr(integ, "result"):
                integ = integ.result()
        try:
            if integ and getattr(integ, "version", None):
                version = integ.version
        except Exception:
            pass
        if version == "unknown":
            try:
                manifest = Path(__file__).resolve().parent / "manifest.json"
                if manifest.exists():
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    vers = data.get("version")
                    if vers:
                        version = str(vers)
            except Exception:
                pass
        return {
            "version": version,
            "label": hub.label,
            "host": hub.host,
            "unit_id": hub.unit,
            "errors_connect": hub.err_connect,
            "errors_read": hub.err_read,
            "count_sensors": sensors,
            "count_binary_sensors": bsens,
            "count_switches": switches,
        }


class QubeMetricSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, hub: WPQubeHub, show_label: bool, kind: str) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._kind = kind
        label = hub.label or "qube1"
        name = {
            "errors_connect": "Qube connect errors",
            "errors_read": "Qube read errors",
            "count_sensors": "Qube sensor count",
            "count_binary_sensors": "Qube binary sensor count",
            "count_switches": "Qube switch count",
        }.get(kind, kind)
        disp = _format_label(label) if show_label else None
        self._attr_name = f"{name} ({disp})" if show_label else name
        self._attr_unique_id = f"qube_metric_{kind}_{label}"
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
            sw_version=_resolve_integration_version(),
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

    def __init__(self, coordinator, hub: WPQubeHub, name: str, unique_suffix: str, kind: str, source: EntityDef) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._name = name
        self._kind = kind
        self._source = source
        self._attr_name = name
        # Make unique per host to support multiple entries
        self._attr_unique_id = f"wp_qube_{unique_suffix}_{hub.label}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=_resolve_integration_version(),
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
