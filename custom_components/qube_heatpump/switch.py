"""Switch platform for Qube Heat Pump."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entity import QubeEntity
from .helpers import entity_data_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .entity_defs import EntityDef
    from .hub import QubeHub

_LOGGER = logging.getLogger(__name__)


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


# Coils the controller keeps on after an acknowledged turn-off while a request
# is still pending (they clear by themselves when the run completes). These
# switches expose a ``pending_request`` attribute instead of pretending the
# write took effect.
PENDING_STATE_SWITCHES = frozenset({"tapw_timeprogram_bms_forced"})

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
        # True after an acknowledged turn-off until the coil actually reads off
        self._turn_off_requested = False
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
        val = self.coordinator.data.get(entity_data_key(self._ent))
        return None if val is None else bool(val)

    @property
    def pending_request(self) -> bool:
        """Return True if a turn-off was acknowledged but the coil still reads on."""
        return self._turn_off_requested and self.is_on is True

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the pending state for coils the controller may hold on."""
        if self._ent.vendor_id not in PENDING_STATE_SWITCHES:
            return None
        return {"pending_request": self.pending_request}

    def _handle_coordinator_update(self) -> None:
        """Forget the pending turn-off once the coil actually reads off."""
        if self._turn_off_requested and self.is_on is False:
            self._turn_off_requested = False
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._turn_off_requested = False
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, True)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._hub.async_connect()
        await self._hub.async_write_switch(self._ent, False)
        self._turn_off_requested = self._ent.vendor_id in PENDING_STATE_SWITCHES
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
        if self.pending_request:
            _LOGGER.info(
                "%s: turn-off acknowledged but the coil is still on; the controller "
                "keeps it on while a DHW request is pending and clears it itself",
                self.entity_id,
            )
