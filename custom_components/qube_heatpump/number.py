"""Number platform for Qube Heat Pump setpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import QubeEntity
from .helpers import entity_data_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .coordinator import QubeCoordinator
    from .entity_defs import EntityDef
    from .hub import QubeHub

PARALLEL_UPDATES = 0

# Allowed (min, max) per writable setpoint register, in °C
SETPOINT_RANGES: dict[str, tuple[float, float]] = {
    "tapw_timeprogram_dhwsetp_nolinq": (40.0, 65.0),  # DHW setpoint
    "usr_pid_heatsetp": (20.0, 65.0),  # heating supply setpoint override
    "usr_pid_coolsetp": (7.0, 25.0),  # cooling supply setpoint override
}
DEFAULT_RANGE = (20.0, 65.0)
DEFAULT_STEP = 0.5

# Redundant number entities to skip (already covered by other entities)
SKIP_NUMBER_VENDOR_IDS = frozenset(
    {
        "setpoint_dhw",  # Redundant - use tapw_timeprogram_dhwsetp_nolinq instead
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube number entities for writable temperature setpoints."""
    data = entry.runtime_data
    async_add_entities(
        QubeSetpointNumber(data.coordinator, data.hub, data.version, ent)
        for ent in data.hub.entities
        if ent.platform == "sensor"
        and ent.writable
        and ent.unit_of_measurement in ("°C", "C")
        and ent.vendor_id not in SKIP_NUMBER_VENDOR_IDS
    )


class QubeSetpointNumber(QubeEntity, NumberEntity):
    """Number entity for Qube setpoints."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = DEFAULT_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        ent: EntityDef,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, hub, version)
        self._ent = ent
        self._key = entity_data_key(ent)

        self._attr_translation_key = ent.translation_key
        # vendor_id gives stable, predictable entity IDs
        self.entity_id = f"number.{self._label}_{ent.vendor_id}"
        # Always scoped per device (host_unit prefix) for multi-device stability
        self._attr_unique_id = self._scoped_uid(f"{self._key}_setpoint")

        self._attr_native_min_value, self._attr_native_max_value = SETPOINT_RANGES.get(
            ent.vendor_id or "", DEFAULT_RANGE
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        val = self.coordinator.data.get(self._key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the setpoint to the device."""
        await self._async_connect()
        await self._async_write_setpoint(self._ent, value)
        await self.coordinator.async_request_refresh()
