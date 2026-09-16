"""Climate platform for Qube Heat Pump virtual thermostat."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    THERMOSTAT_COLD_TOLERANCE,
    THERMOSTAT_HOT_TOLERANCE,
    THERMOSTAT_MAX_TEMP,
    THERMOSTAT_MIN_TEMP,
    THERMOSTAT_SENSOR_TIMEOUT,
    THERMOSTAT_STEP,
)
from .entity import QubeEntity
from .helpers import entity_data_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .coordinator import QubeCoordinator
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


class QubeVirtualThermostat(QubeEntity, RestoreEntity, ClimateEntity):
    """Virtual thermostat that controls Qube via modbus_demand and bms_summerwinter.

    The thermostat is driven by an external temperature sensor, not by the
    coordinator; the coordinator link is used to keep ``_is_heating`` /
    ``_is_cooling`` in step with the real ``modbus_demand`` coil (e.g. after a
    user toggles the switch manually) and to share the device info.
    """

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

    def __init__(
        self,
        entry: QubeConfigEntry,
        hub: QubeHub,
        coordinator: QubeCoordinator,
        sensor_entity_id: str,
        demand_switch: EntityDef,
        summer_switch: EntityDef,
        version: str,
    ) -> None:
        """Initialize the virtual thermostat."""
        super().__init__(coordinator, hub, version)
        self._entry = entry
        self._sensor_entity_id = sensor_entity_id
        self._demand_switch = demand_switch
        self._summer_switch = summer_switch

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
        # Serialises control passes: sensor events, the timeout check and
        # service calls each await several Modbus writes and must not
        # interleave.
        self._control_lock = asyncio.Lock()

        self.entity_id = f"climate.{self._label}_thermostat"
        self._attr_unique_id = self._scoped_uid("thermostat")

    @property
    def available(self) -> bool:
        """Always available.

        The thermostat's own state (mode, setpoint, external temperature) is
        meaningful while the heat pump is unreachable, and its writes fail
        gracefully and are retried. Following the coordinator would also make
        RestoreEntity dump "unavailable" on a restart during an outage and
        lose the mode and setpoint.
        """
        return True

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
                    self._target_temp = min(
                        max(float(temp), THERMOSTAT_MIN_TEMP), THERMOSTAT_MAX_TEMP
                    )
            # Resume the running action so hysteresis holds across a restart;
            # the coil reconciliation below overrides it if the pump disagrees.
            action = last_state.attributes.get(ATTR_HVAC_ACTION)
            self._is_heating = action == HVACAction.HEATING
            self._is_cooling = action == HVACAction.COOLING

        # Seed the coil-derived state from the last poll
        self._reconcile_with_coils()

        # Read initial sensor state
        self._update_temp_from_state(self.hass.states.get(self._sensor_entity_id))
        self._sensor_last_seen = time.monotonic()

        # Listen for sensor state changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._sensor_entity_id],
                self._async_sensor_changed,
            )
        )

        # Periodic timeout check
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_check_timeout,
                timedelta(seconds=_TIMEOUT_CHECK_INTERVAL),
            )
        )

        # Ensure correct switch states for restored mode and run initial control
        await self._async_control_heating()

    async def async_will_remove_from_hass(self) -> None:
        """Turn demand off if this thermostat switched it on.

        This runs on every removal: options reload, integration unload and
        Home Assistant shutdown. Leaving demand on without the thermostat
        would let the heat pump run unattended, so the safety-off is kept
        for all of them; after a reload the initial control pass switches
        demand back on within the same second if it is still needed. In OFF
        mode (or when idle) the coil is not ours and is left alone.
        """
        await self._async_stop_demand()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reconcile with the polled coils, then publish state."""
        self._reconcile_with_coils()
        super()._handle_coordinator_update()

    def _coil_value(self, ent: EntityDef) -> bool | None:
        """Return the last polled value of a switch coil, or None if unknown."""
        data = self.coordinator.data or {}
        value = data.get(entity_data_key(ent))
        return None if value is None else bool(value)

    @callback
    def _reconcile_with_coils(self) -> None:
        """Bring the action flags in line with the real modbus_demand coil.

        A coil that reads off while we believe we are heating/cooling means
        someone (user, controller) switched demand off behind our back: drop
        the flag so the next evaluation can re-assert it. A coil that reads on
        while we are idle in an active mode is adopted, so hysteresis ends it
        and ``hvac_action`` reflects what the heat pump is doing. In OFF mode
        the thermostat does not own the coil and leaves it alone.
        """
        summer = self._coil_value(self._summer_switch)
        if summer is not None:
            self._summer_mode_known = summer

        demand = self._coil_value(self._demand_switch)
        if demand is None or self._hvac_mode == HVACMode.OFF:
            return
        active = self._is_heating or self._is_cooling
        if not demand and active:
            _LOGGER.debug("modbus_demand reads off; thermostat action reset to idle")
            self._is_heating = False
            self._is_cooling = False
        elif demand and not active:
            cooling = self._hvac_mode == HVACMode.COOL or (
                self._hvac_mode == HVACMode.HEAT_COOL and summer is True
            )
            _LOGGER.debug(
                "modbus_demand reads on; thermostat adopts %s",
                "cooling" if cooling else "heating",
            )
            self._is_cooling = cooling
            self._is_heating = not cooling

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
        """Periodic check for sensor timeout.

        ``_sensor_last_seen`` is set when the entity is added and on every
        valid reading, so the timeout also trips when the sensor has never
        delivered a usable value since startup.
        """
        if self._sensor_timed_out:
            return
        elapsed = time.monotonic() - self._sensor_last_seen
        if elapsed <= THERMOSTAT_SENSOR_TIMEOUT:
            return
        _LOGGER.warning(
            "Thermostat sensor %s timed out after %ds; turning off demand",
            self._sensor_entity_id,
            int(elapsed),
        )
        self._current_temp = None
        self._sensor_timed_out = True
        self._entry.runtime_data.thermostat_sensor_timed_out = True
        # With no temperature the control pass stops demand if we believe
        # it is on, and leaves it alone otherwise.
        await self._async_control_heating()
        self.async_write_ha_state()

    async def _async_control_heating(self) -> None:
        """Evaluate thermostat logic and set switch states (serialised)."""
        async with self._control_lock:
            await self._async_control_heating_locked()

    async def _async_control_heating_locked(self) -> None:
        """Evaluate thermostat logic; caller holds ``_control_lock``.

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
                # Set both flags: the refresh inside _async_set_demand may
                # already have adopted the coil under the other action.
                if await self._async_set_demand(True):
                    self._is_heating, self._is_cooling = True, False
            elif too_hot and self._is_heating:
                await self._async_stop_demand()
        else:
            if self._is_heating:
                await self._async_stop_demand()
            if not await self._async_ensure_summer_mode(True):
                return
            if too_hot and not self._is_cooling:
                if await self._async_set_demand(True):
                    self._is_heating, self._is_cooling = False, True
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
        await self.coordinator.async_request_refresh()
        return True

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
        await self.coordinator.async_request_refresh()
        return True
