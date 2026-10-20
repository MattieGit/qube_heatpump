"""Water heater platform for Qube Heat Pump domestic hot water."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .entity import QubeEntity
from .helpers import entity_data_key
from .number import SETPOINT_RANGES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .coordinator import QubeCoordinator
    from .entity_defs import EntityDef
    from .hub import QubeHub

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

DHW_TEMPERATURE = "temp_dhw"
DHW_SETPOINT = "tapw_timeprogram_dhwsetp_nolinq"  # register 173
DHW_FORCED = "tapw_timeprogram_bms_forced"

# Performance is the forced DHW run; heat pump is normal operation
OPERATION_MODES = [STATE_HEAT_PUMP, STATE_PERFORMANCE]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qube domestic hot water heater."""
    data = entry.runtime_data
    by_vendor_id = {ent.vendor_id: ent for ent in data.hub.entities}
    temperature = by_vendor_id.get(DHW_TEMPERATURE)
    setpoint = by_vendor_id.get(DHW_SETPOINT)
    forced = by_vendor_id.get(DHW_FORCED)
    if temperature is None or setpoint is None or forced is None:
        _LOGGER.debug("DHW registers missing; skipping water heater creation")
        return

    async_add_entities(
        [
            QubeWaterHeater(
                data.coordinator, data.hub, data.version, temperature, setpoint, forced
            )
        ]
    )


class QubeWaterHeater(QubeEntity, WaterHeaterEntity):
    """Domestic hot water: DHW temperature, setpoint and the forced run."""

    _attr_operation_list = OPERATION_MODES
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_target_temperature_step = 0.5
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "dhw"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        temperature: EntityDef,
        setpoint: EntityDef,
        forced: EntityDef,
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, hub, version)
        self._setpoint = setpoint
        self._forced = forced
        self._temperature_key = entity_data_key(temperature)
        self._setpoint_key = entity_data_key(setpoint)
        self._forced_key = entity_data_key(forced)
        self._attr_min_temp, self._attr_max_temp = SETPOINT_RANGES[DHW_SETPOINT]

        self.entity_id = f"water_heater.{self._label}_dhw"
        self._attr_unique_id = self._scoped_uid("dhw")

    @property
    def current_temperature(self) -> float | None:
        """Return the DHW temperature."""
        return self._read_float(self._temperature_key)

    @property
    def target_temperature(self) -> float | None:
        """Return the DHW setpoint (register 173)."""
        return self._read_float(self._setpoint_key)

    @property
    def current_operation(self) -> str | None:
        """Return performance while the forced DHW run is on."""
        forced = self.coordinator.data.get(self._forced_key)
        if forced is None:
            return None
        return STATE_PERFORMANCE if forced else STATE_HEAT_PUMP

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the DHW setpoint."""
        await self._async_connect()
        await self._async_write_setpoint(self._setpoint, kwargs[ATTR_TEMPERATURE])
        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Start (performance) or stop (heat pump) the forced DHW run."""
        await self._async_connect()
        await self._async_write_switch(
            self._forced, operation_mode == STATE_PERFORMANCE
        )
        await self.coordinator.async_request_refresh()

    def _read_float(self, key: str) -> float | None:
        value = self.coordinator.data.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
