"""Switch platform for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entity import QubeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import EntityDef, QubeHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube switches."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"

    entities: list[SwitchEntity] = []
    for ent in hub.entities:
        if ent.platform != "switch":
            continue
        if ent.vendor_id in {"bms_sgready_a", "bms_sgready_b"}:
            continue
        entities.append(QubeSwitch(coordinator, hub, ent, version))

    async_add_entities(entities)

    # Cleanup deprecated SG Ready entities (check both old and new unique_id formats)
    registry = er.async_get(hass)
    to_remove_base = ["bms_sgready_a", "bms_sgready_b"]
    for base in to_remove_base:
        # Check for old format (non-scoped)
        entity_id = registry.async_get_entity_id("switch", DOMAIN, base)
        if entity_id:
            registry.async_remove(entity_id)
        # Check for new format (scoped with host_unit)
        scoped_uid = f"{hub.host}_{hub.unit}_{base}"
        entity_id = registry.async_get_entity_id("switch", DOMAIN, scoped_uid)
        if entity_id:
            registry.async_remove(entity_id)


# Switches that should appear in Controls (no entity_category) instead of Configuration
CONTROL_SWITCHES = frozenset({
    "modbus_demand",
    "tapw_timeprogram_bms_forced",
    "bms_summerwinter",
    "antilegionella_frcstart_ant",
})


class QubeSwitch(QubeEntity, SwitchEntity):
    """Qube switch entity."""

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        ent: EntityDef,
        version: str = "unknown",
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, hub, version)
        self._ent = ent
        # Control switches go in Controls section, others in Configuration
        if ent.vendor_id not in CONTROL_SWITCHES:
            self._attr_entity_category = EntityCategory.CONFIG
        if ent.vendor_id in {"bms_sgready_a", "bms_sgready_b"}:
            self._attr_entity_registry_visible_default = False
        # Use vendor_id for stable, predictable entity IDs
        if ent.vendor_id:
            self.entity_id = f"switch.{self._label}_{ent.vendor_id}"
        if ent.translation_key:
            self._attr_translation_key = ent.translation_key
        else:
            self._attr_name = str(ent.name)
        # Always scope unique_id per device (host_unit prefix) to ensure stability
        # when adding/removing devices - prevents entity duplication
        if ent.unique_id:
            self._attr_unique_id = self._scoped_uid(ent.unique_id)
        else:
            suffix = f"{ent.write_type or 'coil'}_{ent.address}".lower()
            base_uid = f"qube_switch_{suffix}"
            self._attr_unique_id = self._scoped_uid(base_uid)

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        key = (
            self._ent.unique_id
            or f"switch_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        )
        val = self.coordinator.data.get(key)
        return None if val is None else bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, False)
        await self.coordinator.async_request_refresh()
