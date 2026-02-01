"""Binary Sensor platform for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import slugify as _slugify

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import EntityDef, QubeHub

HIDDEN_VENDOR_IDS = {
    "dout_threewayvlv_val",
    "dout_fourwayvlv_val",
}

# Vendor IDs that should be classified as problem/alarm sensors
ALARM_VENDOR_IDS = {
    "al_maxtime_antileg_active",
    "al_maxtime_dhw_active",
    "al_dewpoint_active",
    "al_underfloorsafety_active",
    "alrm_flw",
    "usralrms",
    "coolingalrms",
    "heatingalrms",
    "alarmmng_al_workinghour",
    "srsalrm",
    "glbal",
    "alarmmng_al_pwrplus",
}

# Vendor IDs that are running/power status sensors
RUNNING_VENDOR_IDS = {
    "dout_srcpmp_val",
    "dout_usrpmp_val",
    "dout_bufferpmp_val",
    "dout_heaterstep1_val",
    "dout_heaterstep2_val",
    "dout_heaterstep3_val",
    "dout_cooling_val",
    "keybonoff",
}


def _derive_binary_device_class(
    vendor_id: str | None,
) -> BinarySensorDeviceClass | None:
    """Derive device class from vendor ID."""
    if not vendor_id:
        return None
    vendor_lower = vendor_id.lower()
    if vendor_id in ALARM_VENDOR_IDS or vendor_lower.startswith("al"):
        return BinarySensorDeviceClass.PROBLEM
    if vendor_id in RUNNING_VENDOR_IDS:
        return BinarySensorDeviceClass.RUNNING
    return None


def _derive_entity_category(vendor_id: str | None) -> EntityCategory | None:
    """Derive entity category from vendor ID."""
    if not vendor_id:
        return None
    vendor_lower = vendor_id.lower()
    # Alarm sensors are diagnostic
    if vendor_id in ALARM_VENDOR_IDS or vendor_lower.startswith("al"):
        return EntityCategory.DIAGNOSTIC
    # Output status sensors (dout_*) are diagnostic
    if vendor_lower.startswith("dout_"):
        return EntityCategory.DIAGNOSTIC
    # Status sensors are diagnostic
    if "status" in vendor_lower or vendor_lower.endswith("_en"):
        return EntityCategory.DIAGNOSTIC
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube binary sensors."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    apply_label = data.apply_label_in_name
    multi_device = data.multi_device
    version = data.version or "unknown"

    entities: list[BinarySensorEntity] = []
    alarm_entities: list[EntityDef] = []
    for ent in hub.entities:
        if ent.platform != "binary_sensor":
            continue
        entities.append(
            QubeBinarySensor(coordinator, hub, apply_label, multi_device, ent, version)
        )
        if _is_alarm_entity(ent):
            alarm_entities.append(ent)

    if alarm_entities:
        entities.append(
            QubeAlarmStatusBinarySensor(
                coordinator,
                hub,
                apply_label,
                multi_device,
                alarm_entities,
                version,
            )
        )

    async_add_entities(entities)


class QubeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Qube binary sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        show_label: bool,
        multi_device: bool,
        ent: EntityDef,
        version: str = "unknown",
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._ent = ent
        self._hub = hub
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._version = version
        if ent.translation_key:
            manual_name = hub.get_friendly_name("binary_sensor", ent.translation_key)
            if manual_name:
                self._attr_name = manual_name
                self._attr_has_entity_name = False
            else:
                self._attr_translation_key = ent.translation_key
                self._attr_has_entity_name = True
        else:
            self._attr_name = str(ent.name)
        if ent.unique_id:
            self._attr_unique_id = ent.unique_id
        else:
            suffix = f"{ent.input_type or 'input'}_{ent.address}".lower()
            base_uid = f"qube_binary_{suffix}"
            self._attr_unique_id = (
                f"{base_uid}_{self._label}" if multi_device else base_uid
            )
        vendor_id = getattr(ent, "vendor_id", None)
        if vendor_id in HIDDEN_VENDOR_IDS:
            self._attr_entity_registry_visible_default = False
            self._attr_entity_registry_enabled_default = False
        # Set device class based on vendor ID
        device_class = _derive_binary_device_class(vendor_id)
        if device_class:
            self._attr_device_class = device_class
        # Set entity category based on vendor ID
        entity_category = _derive_entity_category(vendor_id)
        if entity_category:
            self._attr_entity_category = entity_category
        if vendor_id:
            # Always include label prefix in entity IDs
            self._attr_suggested_object_id = _slugify(f"{self._label}_{vendor_id}")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        key = (
            self._ent.unique_id
            or f"binary_sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        )
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)


class QubeAlarmStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Aggregate binary sensor for Qube alarm status."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        show_label: bool,
        multi_device: bool,
        alarm_entities: list[EntityDef],
        version: str = "unknown",
    ) -> None:
        """Initialize the alarm status binary sensor."""
        super().__init__(coordinator)
        self._hub = hub
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        self._tied_entities = list(alarm_entities)
        base_unique = "qube_alarm_sensors_state"
        self._attr_unique_id = (
            f"{base_unique}_{self._label}" if self._multi_device else base_unique
        )
        self._attr_translation_key = "qube_alarm_sensors_active"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:alarm-light"
        self._keys = [_entity_state_key(ent) for ent in alarm_entities]
        # Always include label prefix in entity IDs
        self._attr_suggested_object_id = f"{self._label}_alarm_sensors"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def is_on(self) -> bool:
        """Return True if any alarm is active."""
        data = self.coordinator.data or {}
        for key in self._keys:
            val = data.get(key)
            if isinstance(val, bool) and val:
                return True
        return False


def _is_alarm_entity(ent: EntityDef) -> bool:
    """Check if entity is an alarm."""
    if ent.platform != "binary_sensor":
        return False
    name = (ent.name or "").lower()
    if "alarm" in name:
        return True
    vendor = (ent.vendor_id or "").lower()
    return vendor.startswith("al")


def _entity_state_key(ent: EntityDef) -> str:
    """Generate state key for entity."""
    if ent.unique_id:
        return ent.unique_id
    suffix = f"{ent.input_type or ent.write_type}_{ent.address}"
    return f"binary_sensor_{suffix}"
