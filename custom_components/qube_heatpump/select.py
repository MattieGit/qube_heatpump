"""Select platform for Qube Heat Pump."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity

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

PARALLEL_UPDATES = 0

# Option strings are part of the public state; automations depend on them.
SGREADY_OPTIONS = ["Off", "Block", "Plus", "Max"]
MODE_TO_BITS = {
    "Off": (False, False),
    "Block": (True, False),
    "Plus": (False, True),
    "Max": (True, True),
}
BITS_TO_MODE = {value: key for key, value in MODE_TO_BITS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qube select entities."""
    data = entry.runtime_data
    hub = data.hub

    sg_a = _find_switch(hub, "bms_sgready_a")
    sg_b = _find_switch(hub, "bms_sgready_b")
    if not sg_a or not sg_b:
        _LOGGER.debug("SG Ready switches missing; skipping select entity creation")
        return

    async_add_entities(
        [QubeSGReadyModeSelect(data.coordinator, hub, data.version, sg_a, sg_b)]
    )


def _find_switch(hub: QubeHub, vendor_id: str) -> EntityDef | None:
    for ent in hub.entities:
        if ent.platform == "switch" and (ent.vendor_id or "").lower() == vendor_id:
            return ent
    return None


class QubeSGReadyModeSelect(QubeEntity, SelectEntity):
    """Select entity for the SG Ready mode, composed of two coils."""

    _attr_options = SGREADY_OPTIONS
    _attr_translation_key = "sgready_mode"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        sgready_a: EntityDef,
        sgready_b: EntityDef,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, hub, version)
        self._ent_a = sgready_a
        self._ent_b = sgready_b
        self._key_a = entity_data_key(sgready_a)
        self._key_b = entity_data_key(sgready_b)

        self.entity_id = f"select.{self._label}_sg_ready_mode"
        # Always scope unique_id per device for stability
        self._attr_unique_id = self._scoped_uid("sgready_mode")

    @property
    def current_option(self) -> str | None:
        """Return the mode encoded by the two coils, or None while either is unknown."""
        current_a = self._read_bool(self._key_a)
        current_b = self._read_bool(self._key_b)
        if current_a is None or current_b is None:
            return None
        return BITS_TO_MODE[(current_a, current_b)]

    async def async_select_option(self, option: str) -> None:
        """Write the coils that differ from the requested mode."""
        target_a, target_b = MODE_TO_BITS[option]
        current_a = self._read_bool(self._key_a)
        current_b = self._read_bool(self._key_b)

        await self._async_connect()
        if current_a != target_a:
            await self._async_write_switch(self._ent_a, target_a)
        if current_b != target_b:
            await self._async_write_switch(self._ent_b, target_b)
        await self.coordinator.async_request_refresh()

    def _read_bool(self, key: str) -> bool | None:
        value = self.coordinator.data.get(key)
        return None if value is None else bool(value)
