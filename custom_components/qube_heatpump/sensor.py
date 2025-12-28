from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_loaded_integration, async_get_integration
from homeassistant.util import dt as dt_util
try:
    from homeassistant.components.sensor import SensorStateClass
except Exception:  # pragma: no cover - fallback for older HA cores
    SensorStateClass = None  # type: ignore[assignment]

from .const import DOMAIN, TARIFF_OPTIONS
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

    base_counts = {
        "sensor": sum(1 for e in hub.entities if e.platform == "sensor"),
        "binary_sensor": sum(1 for e in hub.entities if e.platform == "binary_sensor"),
        "switch": sum(1 for e in hub.entities if e.platform == "switch"),
    }

    extra_counts = {"sensor": 0, "binary_sensor": 0, "switch": 0}

    entities: list[SensorEntity] = []

    def _translated(name: str, key: str | None = None) -> str:
        return hub.translate_name(key, name)

    def _computed_object_base(name: str, use_prefix: bool) -> str:
        """Return the computed sensor object_id base, optionally stripping the qube_ prefix."""

        slug = _slugify(name)
        if use_prefix:
            return slug
        if slug.startswith("qube_"):
            return slug[len("qube_"):]
        return slug

    def _add_sensor_entity(entity: SensorEntity, include_in_sensor_total: bool = True) -> None:
        if include_in_sensor_total:
            extra_counts["sensor"] += 1
        entities.append(entity)

    counts_holder: Dict[str, Optional[Dict[str, int]]] = {"value": None}

    def _get_counts() -> Optional[Dict[str, int]]:
        return counts_holder["value"]

    # Surface the resolved host IP as its own diagnostic sensor
    _add_sensor_entity(QubeIPAddressSensor(coordinator, hub, apply_label, multi_device, version))

    # Add key diagnostic metrics as separate sensors so users can mark them as
    # Preferred on the device page for quick visibility.
    for kind in (
        "errors_connect",
        "errors_read",
        "count_sensors",
        "count_binary_sensors",
        "count_switches",
    ):
        include = not kind.startswith("count_") or kind == "count_sensors"
        if kind in ("count_sensors", "count_binary_sensors", "count_switches"):
            include = False
        _add_sensor_entity(
            QubeMetricSensor(
                coordinator,
                hub,
                apply_label,
                multi_device,
                version,
                kind=kind,
                counts_provider=_get_counts,
            ),
            include_in_sensor_total=include,
        )

    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        _add_sensor_entity(
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
        status_name = _translated("Status warmtepomp")
        _add_sensor_entity(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name=status_name,
                unique_suffix="status_full",
                kind="status",
                source=status_src,
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
                object_base=_computed_object_base("Status warmtepomp", apply_label),
            )
        )

    # 2) Qube Driewegklep SSW/CV status (binary sensor address 4)
    drie_src = _find_binary_by_address(hub, 4)
    if drie_src is not None:
        drie_name = _translated("Qube Driewegklep SSW/CV status")
        _add_sensor_entity(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name=drie_name,
                unique_suffix="driewegklep_dhw_cv",
                kind="drieweg",
                source=drie_src,
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
                object_base=_computed_object_base("Qube Driewegklep SSW/CV status", apply_label),
            )
        )

    # 3) Qube Vierwegklep verwarmen/koelen status (binary sensor address 2)
    vier_src = _find_binary_by_address(hub, 2)
    if vier_src is not None:
        vier_name = _translated("Qube Vierwegklep verwarmen/koelen status")
        _add_sensor_entity(
            WPQubeComputedSensor(
                coordinator,
                hub,
                name=vier_name,
                unique_suffix="vierwegklep_verwarmen_koelen",
                kind="vierweg",
                source=vier_src,
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
                object_base=_computed_object_base("Qube Vierwegklep verwarmen/koelen status", apply_label),
            )
        )

    standby_power = QubeStandbyPowerSensor(coordinator, hub, apply_label, multi_device, version)
    standby_energy = QubeStandbyEnergySensor(coordinator, hub, apply_label, multi_device, version)
    total_energy = QubeTotalEnergyIncludingStandbySensor(
        coordinator,
        hub,
        apply_label,
        multi_device,
        version,
        base_unique_id=_energy_unique_id(hub.label, multi_device),
        standby_sensor=standby_energy,
    )

    _add_sensor_entity(standby_power)
    _add_sensor_entity(standby_energy)
    _add_sensor_entity(total_energy)

    tracker = hass.data[DOMAIN][entry.entry_id].get("tariff_tracker")
    if tracker is None:
        tracker = TariffEnergyTracker(
            base_key=_energy_unique_id(hub.label, multi_device),
            binary_key=_binary_unique_id(hub.label, multi_device),
            tariffs=list(TARIFF_OPTIONS),
        )
        hass.data[DOMAIN][entry.entry_id]["tariff_tracker"] = tracker
    initial_data = coordinator.data or {}
    tracker.set_initial_total(initial_data.get(tracker.base_key))

    # Track thermic energy per tariff (CV/SWW) in parallel.
    thermic_tracker = hass.data[DOMAIN][entry.entry_id].get("thermic_tariff_tracker")
    if thermic_tracker is None:
        thermic_tracker = TariffEnergyTracker(
            base_key=_thermic_energy_unique_id(hub.label, multi_device),
            binary_key=_binary_unique_id(hub.label, multi_device),
            tariffs=list(TARIFF_OPTIONS),
        )
        hass.data[DOMAIN][entry.entry_id]["thermic_tariff_tracker"] = thermic_tracker
    thermic_tracker.set_initial_total(initial_data.get(thermic_tracker.base_key))

    # Daily trackers for SCOP (reset each day).
    daily_electric_tracker = hass.data[DOMAIN][entry.entry_id].get("daily_tariff_tracker")
    if daily_electric_tracker is None:
        daily_electric_tracker = TariffEnergyTracker(
            base_key=_energy_unique_id(hub.label, multi_device),
            binary_key=_binary_unique_id(hub.label, multi_device),
            tariffs=list(TARIFF_OPTIONS),
            reset_period="day",
        )
        hass.data[DOMAIN][entry.entry_id]["daily_tariff_tracker"] = daily_electric_tracker
    daily_electric_tracker.set_initial_total(initial_data.get(daily_electric_tracker.base_key))

    daily_thermic_tracker = hass.data[DOMAIN][entry.entry_id].get("daily_thermic_tariff_tracker")
    if daily_thermic_tracker is None:
        daily_thermic_tracker = TariffEnergyTracker(
            base_key=_thermic_energy_unique_id(hub.label, multi_device),
            binary_key=_binary_unique_id(hub.label, multi_device),
            tariffs=list(TARIFF_OPTIONS),
            reset_period="day",
        )
        hass.data[DOMAIN][entry.entry_id]["daily_thermic_tariff_tracker"] = daily_thermic_tracker
    daily_thermic_tracker.set_initial_total(initial_data.get(daily_thermic_tracker.base_key))

    _add_sensor_entity(
        QubeTariffEnergySensor(
            coordinator,
            hub,
            tracker,
            tariff="CV",
            name_suffix=_translated("Elektrisch verbruik CV (maand)"),
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeTariffEnergySensor(
            coordinator,
            hub,
            tracker,
            tariff="SWW",
            name_suffix=_translated("Elektrisch verbruik SWW (maand)"),
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeTariffTotalEnergySensor(
            coordinator,
            hub,
            thermic_tracker,
            name_suffix=_translated("Thermische opbrengst (maand)", "thermische_opbrengst_maand"),
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
            base_unique=THERMIC_TOTAL_MONTHLY_UNIQUE_BASE,
            object_base="thermische_opbrengst_maand",
        )
    )
    _add_sensor_entity(
        QubeTariffEnergySensor(
            coordinator,
            hub,
            thermic_tracker,
            tariff="CV",
            name_suffix=_translated(
                "Thermische opbrengst CV (maand)",
                "thermische_opbrengst_cv_maand",
            ),
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
            base_unique=THERMIC_TARIFF_SENSOR_BASE,
            object_base=THERMIC_TARIFF_SENSOR_BASE,
        )
    )
    _add_sensor_entity(
        QubeTariffEnergySensor(
            coordinator,
            hub,
            thermic_tracker,
            tariff="SWW",
            name_suffix=_translated(
                "Thermische opbrengst SWW (maand)",
                "thermische_opbrengst_sww_maand",
            ),
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
            base_unique=THERMIC_TARIFF_SENSOR_BASE,
            object_base=THERMIC_TARIFF_SENSOR_BASE,
        )
    )

    # Monthly SCOP (thermic / electric), overall and per tariff.
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=tracker,
            thermic_tracker=thermic_tracker,
            scope="total",
            name=_translated("SCOP (maand)", "scop_maand"),
            unique_base=SCOP_TOTAL_UNIQUE_BASE,
            object_base="scop_maand",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=tracker,
            thermic_tracker=thermic_tracker,
            scope="CV",
            name=_translated("SCOP CV (maand)", "scop_cv_maand"),
            unique_base=SCOP_CV_UNIQUE_BASE,
            object_base="scop_cv_maand",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=tracker,
            thermic_tracker=thermic_tracker,
            scope="SWW",
            name=_translated("SCOP SWW (maand)", "scop_sww_maand"),
            unique_base=SCOP_SWW_UNIQUE_BASE,
            object_base="scop_sww_maand",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )

    # Daily SCOP (thermic / electric), overall and per tariff.
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=daily_electric_tracker,
            thermic_tracker=daily_thermic_tracker,
            scope="total",
            name=_translated("SCOP (dag)", "scop_dag"),
            unique_base=SCOP_TOTAL_DAILY_UNIQUE_BASE,
            object_base="scop_dag",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=daily_electric_tracker,
            thermic_tracker=daily_thermic_tracker,
            scope="CV",
            name=_translated("SCOP CV (dag)", "scop_cv_dag"),
            unique_base=SCOP_CV_DAILY_UNIQUE_BASE,
            object_base="scop_cv_dag",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )
    _add_sensor_entity(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=daily_electric_tracker,
            thermic_tracker=daily_thermic_tracker,
            scope="SWW",
            name=_translated("SCOP SWW (dag)", "scop_sww_dag"),
            unique_base=SCOP_SWW_DAILY_UNIQUE_BASE,
            object_base="scop_sww_dag",
            show_label=apply_label,
            multi_device=multi_device,
            version=version,
        )
    )

    info_sensor = QubeInfoSensor(
        coordinator,
        hub,
        apply_label,
        multi_device,
        version,
        total_counts=None,
    )
    _add_sensor_entity(info_sensor)

    final_counts = {
        "sensor": base_counts["sensor"] + extra_counts["sensor"],
        "binary_sensor": base_counts["binary_sensor"],
        "switch": base_counts["switch"],
    }

    info_sensor._total_counts = final_counts
    counts_holder["value"] = final_counts

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
            if self._show_label:
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
        if desired and self._show_label and not str(desired).endswith(self._label):
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
        total_counts: Optional[Dict[str, int]] = None,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._version = str(version) if version else "unknown"
        self._total_counts = total_counts or {}
        label = hub.label or "qube1"
        self._attr_name = hub.translate_name("qube_info", "Qube info")
        self._attr_unique_id = (
            f"qube_info_sensor_{label}" if self._multi_device else "qube_info_sensor"
        )
        self._state = "ok"
        self._attr_suggested_object_id = "qube_info"
        if self._show_label:
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
        counts = self._total_counts
        sensors = counts.get("sensor")
        bsens = counts.get("binary_sensor")
        switches = counts.get("switch")
        if sensors is None or bsens is None or switches is None:
            sensors = sensors if sensors is not None else sum(1 for e in hub.entities if e.platform == "sensor")
            bsens = bsens if bsens is not None else sum(1 for e in hub.entities if e.platform == "binary_sensor")
            switches = switches if switches is not None else sum(1 for e in hub.entities if e.platform == "switch")
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
        desired_obj = self._attr_suggested_object_id or "qube_info"
        if self._show_label:
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


class QubeIPAddressSensor(CoordinatorEntity, SensorEntity):
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
        self._version = str(version) if version else "unknown"
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        label = hub.label or "qube1"
        base_name = hub.translate_name("qube_ip_address", "Qube IP address")
        self._attr_name = base_name
        base_uid = "qube_ip_address"
        self._attr_unique_id = f"{base_uid}_{label}" if self._multi_device else base_uid
        self._attr_suggested_object_id = base_uid
        if self._show_label:
            self._attr_suggested_object_id = _slugify(f"{base_uid}_{label}")
        if hasattr(SensorDeviceClass, "IP"):
            try:
                self._attr_device_class = SensorDeviceClass.IP
            except Exception:
                self._attr_device_class = None
        self._attr_icon = "mdi:ip"

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
    def native_value(self) -> str | None:
        return self._hub.resolved_ip or self._hub.host

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        desired_obj = self._attr_suggested_object_id or "qube_ip_address"
        if self._show_label:
            desired_obj = _slugify(f"qube_ip_address_{self._hub.label}")
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_obj)


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
        counts_provider: Optional[Callable[[], Optional[Dict[str, int]]]] = None,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._kind = kind
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._version = version
        self._counts_provider = counts_provider
        label = hub.label or "qube1"
        fallback_name = {
            "errors_connect": "Qube connect errors",
            "errors_read": "Qube read errors",
            "count_sensors": "Qube sensor count",
            "count_binary_sensors": "Qube binary sensor count",
            "count_switches": "Qube switch count",
        }.get(kind, kind.replace("_", " "))
        self._attr_name = hub.translate_name(f"qube_metric_{kind}", fallback_name)
        base_uid = f"qube_metric_{kind}"
        self._attr_unique_id = f"{base_uid}_{label}" if self._multi_device else base_uid
        self._attr_suggested_object_id = _slugify(base_uid)
        if self._show_label:
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
            counts = self._counts_provider() if self._counts_provider else None
            if counts:
                return counts.get("sensor", 0)
            return sum(1 for e in hub.entities if e.platform == "sensor")
        if self._kind == "count_binary_sensors":
            counts = self._counts_provider() if self._counts_provider else None
            if counts:
                return counts.get("binary_sensor", 0)
            return sum(1 for e in hub.entities if e.platform == "binary_sensor")
        if self._kind == "count_switches":
            counts = self._counts_provider() if self._counts_provider else None
            if counts:
                return counts.get("switch", 0)
            return sum(1 for e in hub.entities if e.platform == "switch")
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        desired_obj = self._attr_suggested_object_id or _slugify(f"qube_metric_{self._kind}")
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_obj)


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


STANDBY_POWER_WATTS = 17.0
STANDBY_POWER_UNIQUE_BASE = "qube_standby_power"
STANDBY_ENERGY_UNIQUE_BASE = "qube_standby_energy"
TOTAL_ENERGY_UNIQUE_BASE = "qube_total_energy_with_standby"


def _append_label(base: str, label: str | None, multi_device: bool) -> str:
    if multi_device and label:
        return f"{base}_{label}"
    return base


def _energy_unique_id(label: str | None, multi_device: bool) -> str:
    base = "generalmng_acumulatedpwr"
    return _append_label(base, label, multi_device)


class QubeStandbyPowerSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._label = hub.label or "qube1"
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._version = version
        self._attr_name = hub.translate_name("standby_vermogen", "Standby vermogen")
        unique = _append_label(STANDBY_POWER_UNIQUE_BASE, hub.label, multi_device)
        self._attr_unique_id = unique
        suggested = STANDBY_POWER_UNIQUE_BASE
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        try:
            self._attr_device_class = SensorDeviceClass.POWER
        except Exception:
            self._attr_device_class = None
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.MEASUREMENT
            except Exception:
                pass
        self._attr_native_unit_of_measurement = "W"
        self._attr_native_value = STANDBY_POWER_WATTS

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )


class QubeStandbyEnergySensor(CoordinatorEntity, RestoreSensor, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._label = hub.label or "qube1"
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._version = version
        self._energy_kwh: float = 0.0
        self._last_update: datetime | None = None
        self._attr_name = hub.translate_name("standby_verbruik", "Standby verbruik")
        unique = _append_label(STANDBY_ENERGY_UNIQUE_BASE, hub.label, multi_device)
        self._attr_unique_id = unique
        suggested = STANDBY_ENERGY_UNIQUE_BASE
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        try:
            self._attr_device_class = SensorDeviceClass.ENERGY
        except Exception:
            self._attr_device_class = None
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            except Exception:
                pass
        self._attr_native_unit_of_measurement = "kWh"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "", "unknown", "unavailable"):
            try:
                self._energy_kwh = float(last_state.state)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0
            self._last_update = last_state.last_changed
        if self._last_update is None:
            self._last_update = dt_util.utcnow()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 3)

    def _integrate(self) -> None:
        now = dt_util.utcnow()
        if self._last_update is None:
            self._last_update = now
            return
        elapsed = (now - self._last_update).total_seconds()
        if elapsed <= 0:
            return
        self._last_update = now
        delta_kwh = (STANDBY_POWER_WATTS / 1000.0) * (elapsed / 3600.0)
        self._energy_kwh += delta_kwh

    def _handle_coordinator_update(self) -> None:
        self._integrate()
        super()._handle_coordinator_update()

    def current_energy(self) -> float:
        self._integrate()
        return self._energy_kwh


class QubeTotalEnergyIncludingStandbySensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        show_label: bool,
        multi_device: bool,
        version: str,
        base_unique_id: str,
        standby_sensor: QubeStandbyEnergySensor,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._label = hub.label or "qube1"
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._version = version
        self._base_unique_id = base_unique_id
        self._standby_sensor = standby_sensor
        self._total_energy: float | None = None
        self._attr_name = hub.translate_name(
            "totaal_elektrisch_verbruik_incl_standby",
            "Totaal elektrisch verbruik (incl. standby)",
        )
        unique = _append_label(TOTAL_ENERGY_UNIQUE_BASE, hub.label, multi_device)
        self._attr_unique_id = unique
        suggested = TOTAL_ENERGY_UNIQUE_BASE
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        try:
            self._attr_device_class = SensorDeviceClass.ENERGY
        except Exception:
            self._attr_device_class = None
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            except Exception:
                pass
        self._attr_native_unit_of_measurement = "kWh"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> float | None:
        return None if self._total_energy is None else round(self._total_energy, 3)

    def _handle_coordinator_update(self) -> None:
        base_value = self.coordinator.data.get(self._base_unique_id)
        standby = self._standby_sensor.current_energy()
        try:
            base_float = float(base_value) if base_value is not None else None
        except (TypeError, ValueError):
            base_float = None
        if base_float is None:
            self._total_energy = None
        else:
            self._total_energy = base_float + standby
        super()._handle_coordinator_update()


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
        object_base: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._name = name
        self._kind = kind
        self._source = source
        self._version = version
        self._multi_device = bool(multi_device)
        self._show_label = bool(show_label)
        self._label = hub.label or "qube1"
        self._object_base = _slugify(object_base) if object_base else _slugify(name)
        self._attr_name = name
        base_unique = f"wp_qube_{unique_suffix}"
        self._attr_unique_id = (
            f"{base_unique}_{self._label}" if self._multi_device else base_unique
        )
        self._attr_suggested_object_id = self._object_base
        if self._show_label:
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
                    text = "Standby"
                else:
                    text = {
                        2: "Alarm",
                        6: "Keyboard off",
                        8: "Compressor start up",
                        9: "Compressor shutdown",
                        15: "Cooling",
                        16: "Heating",
                        17: "Start fail",
                        22: "Heating DHW",
                    }.get(code, "Unknown state")
                return self._hub.translate_name(f"status_value_{_slugify(text)}", text)
            if self._kind == "drieweg":
                text = "DHW" if bool(val) else "CV"
                return self._hub.translate_name(f"status_value_{_slugify(text)}", text)
            if self._kind == "vierweg":
                text = "Verwarmen" if bool(val) else "Koelen"
                return self._hub.translate_name(f"status_value_{_slugify(text)}", text)
        except Exception:
            return None
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        suffix = f"_{self._label}" if self._show_label else ""
        desired = f"{self._object_base}{suffix}"
        await _async_ensure_entity_id(self.hass, self.entity_id, _slugify(str(desired)))
STANDBY_POWER_WATTS = 17.0
STANDBY_POWER_UNIQUE_BASE = "qube_standby_power"
STANDBY_ENERGY_UNIQUE_BASE = "qube_standby_energy"
TOTAL_ENERGY_UNIQUE_BASE = "qube_total_energy_with_standby"
BINARY_TARIFF_UNIQUE_ID = "dout_threewayvlv_val"
TARIFF_SENSOR_BASE = "qube_energy_tariff"
THERMIC_TARIFF_SENSOR_BASE = "qube_thermic_energy_tariff"
THERMIC_TOTAL_MONTHLY_UNIQUE_BASE = "qube_thermic_energy_monthly"
SCOP_TOTAL_UNIQUE_BASE = "qube_scop_monthly"
SCOP_CV_UNIQUE_BASE = "qube_scop_cv_monthly"
SCOP_SWW_UNIQUE_BASE = "qube_scop_sww_monthly"
SCOP_TOTAL_DAILY_UNIQUE_BASE = "qube_scop_daily"
SCOP_CV_DAILY_UNIQUE_BASE = "qube_scop_cv_daily"
SCOP_SWW_DAILY_UNIQUE_BASE = "qube_scop_sww_daily"
# Drop transient SCOP spikes above this threshold to avoid chart pollution.
SCOP_MAX_EXPECTED = 10.0


def _start_of_month(dt_value: datetime) -> datetime:
    return dt_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_day(dt_value: datetime) -> datetime:
    return dt_value.replace(hour=0, minute=0, second=0, microsecond=0)


def _append_label(base: str, label: str | None, multi_device: bool) -> str:
    if multi_device and label:
        return f"{base}_{label}"
    return base


def _energy_unique_id(label: str | None, multi_device: bool) -> str:
    base = "generalmng_acumulatedpwr"
    return _append_label(base, label, multi_device)


def _thermic_energy_unique_id(label: str | None, multi_device: bool) -> str:
    base = "generalmng_acumulatedthermic"
    return _append_label(base, label, multi_device)


def _binary_unique_id(label: str | None, multi_device: bool) -> str:
    return _append_label(BINARY_TARIFF_UNIQUE_ID, label, multi_device)


class TariffEnergyTracker:
    """Track split energy totals for CV/SWW."""

    def __init__(
        self,
        base_key: str,
        binary_key: str,
        tariffs: List[str],
        reset_period: str = "month",
    ) -> None:
        self.base_key = base_key
        self.binary_key = binary_key
        self.tariffs = list(tariffs)
        self._totals: Dict[str, float] = {tariff: 0.0 for tariff in tariffs}
        self._current_tariff: str = tariffs[0]
        self._last_total: float | None = None
        self._reset_period = reset_period
        self._last_reset: datetime = self._cycle_start(dt_util.utcnow())
        self._last_token: datetime | None = None

    @property
    def current_tariff(self) -> str:
        return self._current_tariff

    @property
    def last_reset(self) -> datetime:
        return self._last_reset

    def restore_total(self, tariff: str, value: float, last_reset: datetime | None) -> None:
        if tariff in self._totals:
            self._totals[tariff] = max(0.0, value)
        if last_reset and last_reset > self._last_reset:
            self._last_reset = last_reset

    def set_initial_total(self, total: float | None) -> None:
        if total is None:
            return
        try:
            self._last_total = float(total)
        except (TypeError, ValueError):
            self._last_total = None

    def _cycle_start(self, dt_value: datetime) -> datetime:
        if self._reset_period == "day":
            return _start_of_day(dt_value)
        return _start_of_month(dt_value)

    def _reset_if_needed(self, reference: datetime | None) -> None:
        now = reference or dt_util.utcnow()
        start = self._cycle_start(now)
        if start > self._last_reset:
            self._last_reset = start
            for tariff in self._totals:
                self._totals[tariff] = 0.0

    def update(self, coordinator_data: dict[str, Any], token: datetime | None) -> None:
        if token is not None and self._last_token is not None and token <= self._last_token:
            self._refresh_current_tariff(coordinator_data)
            return

        if token is not None:
            self._last_token = token

        base_val = coordinator_data.get(self.base_key)
        try:
            base_float = float(base_val) if base_val is not None else None
        except (TypeError, ValueError):
            base_float = None

        self._refresh_current_tariff(coordinator_data)

        if base_float is None:
            return

        if self._last_total is None:
            self._last_total = base_float
            return

        delta = base_float - self._last_total
        self._last_total = base_float
        if delta <= 0:
            return

        reference = token or dt_util.utcnow()
        self._reset_if_needed(reference)
        self._totals[self._current_tariff] += delta

    def _refresh_current_tariff(self, coordinator_data: dict[str, Any]) -> None:
        state = coordinator_data.get(self.binary_key)
        if isinstance(state, bool):
            self._current_tariff = "SWW" if state else "CV"

    def get_total(self, tariff: str) -> float:
        return self._totals.get(tariff, 0.0)


class QubeTariffEnergySensor(CoordinatorEntity, RestoreSensor, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        tracker: TariffEnergyTracker,
        tariff: str,
        name_suffix: str,
        show_label: bool,
        multi_device: bool,
        version: str,
        base_unique: str | None = None,
        object_base: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._tracker = tracker
        self._tariff = tariff
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        self._attr_name = name_suffix
        base_uid = f"{(base_unique or TARIFF_SENSOR_BASE)}_{tariff.lower()}"
        self._attr_unique_id = _append_label(base_uid, hub.label, multi_device)
        suggested_base = object_base or base_uid
        suggested = suggested_base
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        try:
            self._attr_device_class = SensorDeviceClass.ENERGY
        except Exception:
            self._attr_device_class = None
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            except Exception:
                pass
        self._attr_native_unit_of_measurement = "kWh"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "", "unknown", "unavailable"):
            try:
                value = float(last_state.state)
            except (TypeError, ValueError):
                value = 0.0
            last_reset: datetime | None = None
            if hasattr(last_state, "last_reset"):
                last_reset = getattr(last_state, "last_reset")
            if not last_reset:
                cycle_start = last_state.attributes.get("cycle_start") if last_state.attributes else None
                if cycle_start:
                    parsed = dt_util.parse_datetime(str(cycle_start))
                    if parsed is not None:
                        last_reset = parsed
            self._tracker.restore_total(self._tariff, value, last_reset)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> float:
        return round(self._tracker.get_total(self._tariff), 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # type: ignore[override]
        return {"cycle_start": self._tracker.last_reset.isoformat()}

    def _handle_coordinator_update(self) -> None:
        token = getattr(self.coordinator, "last_update_success_time", None)
        data = self.coordinator.data or {}
        self._tracker.update(data, token)
        super()._handle_coordinator_update()


class QubeTariffTotalEnergySensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        tracker: TariffEnergyTracker,
        name_suffix: str,
        show_label: bool,
        multi_device: bool,
        version: str,
        base_unique: str,
        object_base: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._tracker = tracker
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        self._attr_name = name_suffix
        self._attr_unique_id = _append_label(base_unique, hub.label, multi_device)
        suggested = object_base
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        try:
            self._attr_device_class = SensorDeviceClass.ENERGY
        except Exception:
            self._attr_device_class = None
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            except Exception:
                pass
        self._attr_native_unit_of_measurement = "kWh"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> float:
        return round(sum(self._tracker.get_total(t) for t in self._tracker.tariffs), 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # type: ignore[override]
        return {"cycle_start": self._tracker.last_reset.isoformat()}

    def _handle_coordinator_update(self) -> None:
        token = getattr(self.coordinator, "last_update_success_time", None)
        data = self.coordinator.data or {}
        self._tracker.update(data, token)
        super()._handle_coordinator_update()


class QubeSCOPSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub: WPQubeHub,
        electric_tracker: TariffEnergyTracker,
        thermic_tracker: TariffEnergyTracker,
        scope: str,
        name: str,
        unique_base: str,
        object_base: str,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._electric = electric_tracker
        self._thermic = thermic_tracker
        self._scope = scope
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        self._attr_name = name
        self._object_base = object_base
        base_uid = unique_base
        if self._multi_device and self._label:
            base_uid = f"{base_uid}_{self._label}"
        self._attr_unique_id = base_uid
        suggested = object_base
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        self._attr_suggested_display_precision = 1
        self._attr_native_unit_of_measurement = "CoP"
        if SensorStateClass:
            try:
                self._attr_state_class = SensorStateClass.TOTAL
            except Exception:
                pass

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        desired = self._object_base
        if self._show_label:
            desired = f"{desired}_{self._label}"
        await _async_ensure_entity_id(self.hass, self.entity_id, _slugify(str(desired)))

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    def _current_totals(self) -> tuple[float | None, float | None]:
        if self._scope == "total":
            elec = sum(self._electric.get_total(t) for t in self._electric.tariffs)
            therm = sum(self._thermic.get_total(t) for t in self._thermic.tariffs)
            return elec, therm
        elec = self._electric.get_total(self._scope)
        therm = self._thermic.get_total(self._scope)
        return elec, therm

    @property
    def native_value(self) -> float | None:
        elec, therm = self._current_totals()
        if elec is None or therm is None:
            return None
        try:
            elec_f = float(elec)
            therm_f = float(therm)
        except (TypeError, ValueError):
            return None
        if elec_f <= 0:
            return None
        scop = therm_f / elec_f
        if scop < 0 or scop > SCOP_MAX_EXPECTED:
            return None
        return round(scop, 1)

    def _handle_coordinator_update(self) -> None:
        token = getattr(self.coordinator, "last_update_success_time", None)
        data = self.coordinator.data or {}
        self._electric.update(data, token)
        self._thermic.update(data, token)
        super()._handle_coordinator_update()
