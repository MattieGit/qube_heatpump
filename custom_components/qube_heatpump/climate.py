"""Climate platform for Qube Heat Pump virtual thermostat."""

from __future__ import annotations

import contextlib
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DOMAIN,
    THERMOSTAT_COLD_TOLERANCE,
    THERMOSTAT_HOT_TOLERANCE,
    THERMOSTAT_MAX_TEMP,
    THERMOSTAT_MIN_TEMP,
    THERMOSTAT_SENSOR_TIMEOUT,
    THERMOSTAT_STEP,
)
from .helpers import entity_data_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .entity_defs import EntityDef
    from .hub import QubeHub

_LOGGER = logging.getLogger(__name__)

_TIMEOUT_CHECK_INTERVAL = 60  # seconds


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube climate entity."""
    if not entry.options.get(CONF_THERMOSTAT_ENABLED):
        return
    sensor_entity_id = entry.options.get(CONF_THERMOSTAT_SENSOR)
    if not sensor_entity_id:
        return

    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"

    # Find the modbus_demand and bms_summerwinter switch EntityDefs
    demand_switch: EntityDef | None = None
    summer_switch: EntityDef | None = None
    for ent in hub.entities:
        if ent.platform != "switch":
            continue
        if ent.vendor_id == "modbus_demand":
            demand_switch = ent
        elif ent.vendor_id == "bms_summerwinter":
            summer_switch = ent

    if demand_switch is None:
        _LOGGER.error("Cannot find modbus_demand switch; thermostat not created")
        return
    if summer_switch is None:
        _LOGGER.error("Cannot find bms_summerwinter switch; thermostat not created")
        return

    async_add_entities(
        [
            QubeVirtualThermostat(
                entry,
                hub,
                coordinator,
                sensor_entity_id,
                demand_switch,
                summer_switch,
                version,
            )
        ]
    )


class QubeVirtualThermostat(RestoreEntity, ClimateEntity):
    """Virtual thermostat that controls Qube via modbus_demand and bms_summerwinter."""

    _attr_has_entity_name = True
    _attr_translation_key = "thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_target_temperature_step = THERMOSTAT_STEP
    _attr_min_temp = THERMOSTAT_MIN_TEMP
    _attr_max_temp = THERMOSTAT_MAX_TEMP
    _attr_should_poll = False

    def __init__(
        self,
        entry: QubeConfigEntry,
        hub: QubeHub,
        coordinator: Any,
        sensor_entity_id: str,
        demand_switch: EntityDef,
        summer_switch: EntityDef,
        version: str,
    ) -> None:
        """Initialize the virtual thermostat."""
        self._hub = hub
        self._entry = entry
        self._coordinator = coordinator
        self._sensor_entity_id = sensor_entity_id
        self._demand_switch = demand_switch
        self._summer_switch = summer_switch
        self._version = version

        self._current_temp: float | None = None
        self._target_temp: float = 20.5
        self._hvac_mode: HVACMode = HVACMode.HEAT
        self._is_heating: bool = False
        self._is_cooling: bool = False
        self._sensor_last_seen: float = time.monotonic()
        self._sensor_timed_out: bool = False
        # Last known bms_summerwinter value: seeded from the coordinator and
        # updated on every successful write, so a write is never skipped on
        # the strength of a poll that predates our own last write.
        self._summer_mode_known: bool | None = None

        self._cancel_state_listener: Any = None
        self._cancel_timeout_check: Any = None

        self.entity_id = f"climate.{hub.label}_thermostat"
        self._attr_unique_id = f"{hub.host}_{hub.unit}_thermostat"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{hub.host}:{hub.unit}")},
            name=hub.device_name,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self._version,
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self._target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running action."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self._is_heating:
            return HVACAction.HEATING
        if self._is_cooling:
            return HVACAction.COOLING
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        self._hvac_mode = hvac_mode
        await self._async_control_heating()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._target_temp = float(temp)
        await self._async_control_heating()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state:
            if last_state.state in (
                HVACMode.OFF,
                HVACMode.HEAT,
                HVACMode.COOL,
                HVACMode.HEAT_COOL,
            ):
                self._hvac_mode = HVACMode(last_state.state)
            if (temp := last_state.attributes.get(ATTR_TEMPERATURE)) is not None:
                with contextlib.suppress(TypeError, ValueError):
                    self._target_temp = float(temp)

        self._summer_mode_known = self._coil_value(self._summer_switch)

        # Read initial sensor state
        self._update_temp_from_state(self.hass.states.get(self._sensor_entity_id))
        self._sensor_last_seen = time.monotonic()

        # Listen for sensor state changes
        self._cancel_state_listener = async_track_state_change_event(
            self.hass,
            [self._sensor_entity_id],
            self._async_sensor_changed,
        )

        # Periodic timeout check
        self._cancel_timeout_check = async_track_time_interval(
            self.hass,
            self._async_check_timeout,
            timedelta(seconds=_TIMEOUT_CHECK_INTERVAL),
        )

        # Ensure correct switch states for restored mode and run initial control
        await self._async_control_heating()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed."""
        if self._cancel_state_listener:
            self._cancel_state_listener()
        if self._cancel_timeout_check:
            self._cancel_timeout_check()

        # Turn off demand to be safe
        await self._async_set_demand(False)

    @callback
    def _update_temp_from_state(self, state: Any) -> None:
        """Update current temperature from a state object."""
        if state is None or state.state in ("unknown", "unavailable"):
            return
        try:
            self._current_temp = float(state.state)
            self._sensor_last_seen = time.monotonic()
            if self._sensor_timed_out:
                self._sensor_timed_out = False
                self._entry.runtime_data.thermostat_sensor_timed_out = False
                _LOGGER.info("Thermostat sensor recovered")
        except (TypeError, ValueError):
            pass

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle sensor state change."""
        new_state = event.data.get("new_state")
        self._update_temp_from_state(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    async def _async_check_timeout(self, _now: Any = None) -> None:
        """Periodic check for sensor timeout."""
        if self._current_temp is None:
            return
        elapsed = time.monotonic() - self._sensor_last_seen
        if elapsed > THERMOSTAT_SENSOR_TIMEOUT and not self._sensor_timed_out:
            _LOGGER.warning(
                "Thermostat sensor %s timed out after %ds; turning off demand",
                self._sensor_entity_id,
                int(elapsed),
            )
            self._current_temp = None
            self._sensor_timed_out = True
            self._entry.runtime_data.thermostat_sensor_timed_out = True
            await self._async_set_demand(False)
            self._is_heating = False
            self._is_cooling = False
            self.async_write_ha_state()

    async def _async_control_heating(self) -> None:
        """Evaluate thermostat logic and set switch states.

        Flags (``_is_heating`` / ``_is_cooling``) only change after the
        corresponding Modbus write succeeded, so a failed write is retried on
        the next evaluation instead of being papered over.
        """
        if self._hvac_mode == HVACMode.OFF or self._current_temp is None:
            # Thermostat off, or no usable temperature: stop for safety.
            await self._async_stop_demand()
            return

        too_cold = self._current_temp <= self._target_temp - THERMOSTAT_COLD_TOLERANCE
        too_hot = self._current_temp >= self._target_temp + THERMOSTAT_HOT_TOLERANCE

        # Decide which action this pass is about. In HEAT_COOL the deadband
        # holds the current action (hysteresis), mirroring HEAT and COOL:
        # heating only stops once too_hot, cooling only once too_cold.
        if self._hvac_mode == HVACMode.HEAT:
            want = HVACAction.HEATING
        elif self._hvac_mode == HVACMode.COOL:
            want = HVACAction.COOLING
        elif too_cold:
            want = HVACAction.HEATING
        elif too_hot:
            want = HVACAction.COOLING
        elif self._is_heating:
            want = HVACAction.HEATING
        elif self._is_cooling:
            want = HVACAction.COOLING
        else:
            return  # HEAT_COOL, idle in the deadband

        if want == HVACAction.HEATING:
            if self._is_cooling:
                # Switching direction: stop before flipping summer/winter.
                await self._async_stop_demand()
            if not await self._async_ensure_summer_mode(False):
                return
            if too_cold and not self._is_heating:
                if await self._async_set_demand(True):
                    self._is_heating = True
            elif too_hot and self._is_heating:
                await self._async_stop_demand()
        else:
            if self._is_heating:
                await self._async_stop_demand()
            if not await self._async_ensure_summer_mode(True):
                return
            if too_hot and not self._is_cooling:
                if await self._async_set_demand(True):
                    self._is_cooling = True
            elif too_cold and self._is_cooling:
                await self._async_stop_demand()

    async def _async_stop_demand(self) -> None:
        """Turn demand off if we believe it is on; clear flags only on success."""
        if not (self._is_heating or self._is_cooling):
            return
        if await self._async_set_demand(False):
            self._is_heating = False
            self._is_cooling = False

    async def _async_set_demand(self, on: bool) -> bool:
        """Set the modbus_demand switch; return True when the write succeeded."""
        try:
            await self._hub.async_connect()
            await self._hub.async_write_switch(self._demand_switch, on)
        except (ConnectionError, OSError) as exc:
            _LOGGER.warning("Failed to set modbus_demand to %s: %s", on, exc)
            return False
        await self._coordinator.async_request_refresh()
        return True

    def _coil_value(self, ent: EntityDef) -> bool | None:
        """Return the last polled value of a switch coil, or None if unknown."""
        data = self._coordinator.data or {}
        value = data.get(entity_data_key(ent))
        return None if value is None else bool(value)

    async def _async_ensure_summer_mode(self, on: bool) -> bool:
        """Ensure bms_summerwinter is in the correct state; True when it is.

        Skips the Modbus write when the last known coil value (last poll or
        our own last write, whichever is newer) already matches; this runs
        on every sensor state-change event. An unknown value is always
        written.
        """
        if self._summer_mode_known is on:
            return True
        try:
            await self._hub.async_connect()
            await self._hub.async_write_switch(self._summer_switch, on)
        except (ConnectionError, OSError) as exc:
            _LOGGER.warning("Failed to set bms_summerwinter to %s: %s", on, exc)
            return False
        self._summer_mode_known = on
        await self._coordinator.async_request_refresh()
        return True
