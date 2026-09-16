"""Binary Sensor platform for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .const import CONF_THERMOSTAT_ENABLED
from .entity import QubeEntity
from .helpers import entity_data_key, is_alarm_entity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .dhw_scheduler import DhwScheduleState
    from .entity_defs import EntityDef
    from .hub import QubeHub

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
    version = data.version or "unknown"

    entities: list[BinarySensorEntity] = []
    alarm_entities: list[EntityDef] = []
    for ent in hub.entities:
        if ent.platform != "binary_sensor":
            continue
        entities.append(QubeBinarySensor(coordinator, hub, ent, version))
        if is_alarm_entity(ent):
            alarm_entities.append(ent)

    if alarm_entities:
        entities.append(
            QubeAlarmStatusBinarySensor(
                coordinator,
                hub,
                alarm_entities,
                version,
            )
        )

    entities.append(QubeEnergyTotalsStaleSensor(coordinator, hub, version))
    entities.append(QubeDhwScheduleBinarySensor(coordinator, hub, entry, version))

    # Add thermostat sensor timeout binary sensor if thermostat is enabled
    if entry.options.get(CONF_THERMOSTAT_ENABLED):
        entities.append(
            QubeThermostatTimeoutSensor(coordinator, hub, entry, version)
        )

    async_add_entities(entities)


class QubeBinarySensor(QubeEntity, BinarySensorEntity):
    """Representation of a Qube binary sensor."""

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        ent: EntityDef,
        version: str = "unknown",
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, hub, version)
        self._ent = ent
        if ent.translation_key:
            self._attr_translation_key = ent.translation_key
        else:
            self._attr_name = str(ent.name)
        # Always scope unique_id per device (host_unit prefix) to ensure stability
        # when adding/removing devices - prevents entity duplication
        if ent.unique_id:
            self._attr_unique_id = self._scoped_uid(ent.unique_id)
        else:
            suffix = f"{ent.input_type or 'input'}_{ent.address}".lower()
            base_uid = f"qube_binary_{suffix}"
            self._attr_unique_id = self._scoped_uid(base_uid)
        vendor_id = getattr(ent, "vendor_id", None)
        # Use vendor_id for stable, predictable entity IDs
        if vendor_id:
            self.entity_id = f"binary_sensor.{self._label}_{vendor_id}"
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

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        val = self.coordinator.data.get(entity_data_key(self._ent))
        return None if val is None else bool(val)


class QubeAlarmStatusBinarySensor(QubeEntity, BinarySensorEntity):
    """Aggregate binary sensor for Qube alarm status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        alarm_entities: list[EntityDef],
        version: str = "unknown",
    ) -> None:
        """Initialize the alarm status binary sensor."""
        super().__init__(coordinator, hub, version)
        self._tied_entities = list(alarm_entities)
        # Always scope unique_id per device for stability
        self._attr_unique_id = self._scoped_uid("alarm_sensors_state")
        self._attr_translation_key = "alarm_sensors_active"
        self.entity_id = f"binary_sensor.{self._label}_alarm_sensors_active"
        self._attr_icon = "mdi:alarm-light"
        self._keys = [entity_data_key(ent) for ent in alarm_entities]

    @property
    def is_on(self) -> bool:
        """Return True if any alarm is active."""
        data = self.coordinator.data or {}
        for key in self._keys:
            val = data.get(key)
            if isinstance(val, bool) and val:
                return True
        return False


class QubeEnergyTotalsStaleSensor(QubeEntity, BinarySensorEntity):
    """Binary sensor that is on while the energy totalisers are not advancing.

    The coordinator flags this when registers 69/71 have not changed for
    15 minutes although the heat pump draws more than a few hundred watts.
    All derived day/month/SCOP sensors depend on those totals.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        version: str = "unknown",
    ) -> None:
        """Initialize the staleness sensor."""
        super().__init__(coordinator, hub, version)
        self._attr_translation_key = "energy_totals_stale"
        self._attr_unique_id = self._scoped_uid("energy_totals_stale")
        self.entity_id = f"binary_sensor.{self._label}_energy_totals_stale"

    @property
    def is_on(self) -> bool:
        """Return True if the energy totals are not advancing."""
        return bool(getattr(self.coordinator, "energy_totals_stale", False))


class QubeDhwScheduleBinarySensor(QubeEntity, BinarySensorEntity):
    """Shows whether the DHW schedule is enabled, with its configuration as attributes.

    Reads ``runtime_data.dhw_schedule`` only; no Modbus traffic is involved.
    Refreshes on coordinator updates and whenever the scheduler fires.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        entry: QubeConfigEntry,
        version: str = "unknown",
    ) -> None:
        """Initialize the schedule sensor."""
        super().__init__(coordinator, hub, version)
        self._entry = entry
        self._attr_translation_key = "dhw_schedule"
        self._attr_unique_id = self._scoped_uid("dhw_schedule")
        self.entity_id = f"binary_sensor.{self._label}_dhw_schedule"

    @property
    def _state(self) -> DhwScheduleState | None:
        return self._entry.runtime_data.dhw_schedule

    async def async_added_to_hass(self) -> None:
        """Subscribe to scheduler state changes."""
        await super().async_added_to_hass()
        if (state := self._state) is not None:
            self.async_on_remove(state.async_add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        """Return True if the DHW schedule option is enabled."""
        state = self._state
        return bool(state is not None and state.enabled)

    @property
    def icon(self) -> str:
        """Water boiler while the window is active, calendar otherwise."""
        state = self._state
        if state is not None and state.window_active:
            return "mdi:water-boiler"
        return "mdi:calendar-clock"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the schedule configuration and run history."""
        state = self._state
        if state is None or not state.enabled:
            return {"window_active": False}
        attrs: dict[str, Any] = {
            "start": state.start_time,
            "end": state.end_time,
            "setpoint_source": state.setpoint_source,
            "window_active": state.window_active,
            "last_start": state.last_start.isoformat() if state.last_start else None,
            "last_end": state.last_end.isoformat() if state.last_end else None,
        }
        if state.setpoint_source == "fixed":
            attrs["fixed_setpoint"] = state.fixed_setpoint
        return attrs


class QubeThermostatTimeoutSensor(QubeEntity, BinarySensorEntity):
    """Binary sensor indicating the thermostat temperature sensor has timed out."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        entry: QubeConfigEntry,
        version: str = "unknown",
    ) -> None:
        """Initialize the timeout sensor."""
        super().__init__(coordinator, hub, version)
        self._entry = entry
        self._attr_translation_key = "thermostat_sensor_timeout"
        self._attr_unique_id = self._scoped_uid("thermostat_sensor_timeout")
        self.entity_id = f"binary_sensor.{self._label}_thermostat_sensor_timeout"

    @property
    def is_on(self) -> bool:
        """Return True if sensor has timed out."""
        return bool(self._entry.runtime_data.thermostat_sensor_timed_out)
