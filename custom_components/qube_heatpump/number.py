"""Number platform for Qube Heat Pump setpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import QubeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import EntityDef, QubeHub


# Default min/max for temperature setpoints
DEFAULT_MIN_TEMP = 20.0
DEFAULT_MAX_TEMP = 65.0
DEFAULT_STEP = 0.5

# Redundant number entities to skip (already covered by other entities)
SKIP_NUMBER_VENDOR_IDS = frozenset({
    "setpoint_dhw",  # Redundant - use tapw_timeprogram_dhwsetp_nolinq instead
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube number entities for setpoints."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"

    entities: list[NumberEntity] = []
    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        if not ent.writable:
            continue
        # Only create number entities for temperature setpoints
        if ent.unit_of_measurement not in ("°C", "C"):
            continue
        # Skip redundant entities
        if ent.vendor_id in SKIP_NUMBER_VENDOR_IDS:
            continue

        entities.append(
            QubeSetpointNumber(
                coordinator,
                hub,
                version,
                ent,
            )
        )

    async_add_entities(entities)


class QubeSetpointNumber(QubeEntity, NumberEntity):
    """Number entity for Qube setpoints."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        version: str,
        ent: EntityDef,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, hub, version)
        self._ent = ent

        # Set name from translation or entity name
        if ent.translation_key:
            self._attr_translation_key = ent.translation_key
        else:
            self._attr_name = str(ent.name)
        # Use vendor_id for stable, predictable entity IDs
        if ent.vendor_id:
            self.entity_id = f"number.{self._label}_{ent.vendor_id}"

        # Always scope unique_id per device (host_unit prefix) to ensure stability
        # when adding/removing devices - prevents entity duplication
        if ent.unique_id:
            base_uid = f"{ent.unique_id}_setpoint"
        else:
            suffix = f"{ent.input_type or 'holding'}_{ent.address}".lower()
            base_uid = f"qube_setpoint_{suffix}"
        self._attr_unique_id = self._scoped_uid(base_uid)

        # Number configuration
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_native_min_value = DEFAULT_MIN_TEMP
        self._attr_native_max_value = DEFAULT_MAX_TEMP
        self._attr_native_step = DEFAULT_STEP
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        key = (
            self._ent.unique_id
            or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        )
        val = self.coordinator.data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the setpoint value."""
        await self._hub.async_connect()
        await self._hub.async_write_setpoint(self._ent, value)
        await self.coordinator.async_request_refresh()
