"""Base entity for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import QubeCoordinator

if TYPE_CHECKING:
    from .entity_defs import EntityDef
    from .hub import QubeHub


class QubeEntity(CoordinatorEntity[QubeCoordinator]):
    """Common base for Qube coordinator entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: QubeCoordinator, hub: QubeHub, version: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._hub = hub
        self._version = str(version) if version else "unknown"
        self._label = hub.label
        self._entry_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=hub.device_name,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self._version,
        )

    def _scoped_uid(self, base: str) -> str:
        """Scope a unique_id to this config entry (stable across host changes)."""
        return f"{self._entry_id}_{base}"

    async def _async_connect(self) -> None:
        """Connect to the device, surfacing a translated error to the caller."""
        try:
            await self._hub.async_connect()
        except ConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="connection_failed",
                translation_placeholders={"host": self._hub.host},
            ) from err

    async def _async_write_switch(self, ent: EntityDef, on: bool) -> None:
        """Write a coil, surfacing a translated error to the caller."""
        try:
            await self._hub.async_write_switch(ent, on)
        except OSError as err:  # ConnectionError from the hub is an OSError
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_switch_failed",
                translation_placeholders={"entity_id": self.entity_id},
            ) from err

    async def _async_write_setpoint(self, ent: EntityDef, value: float) -> None:
        """Write a holding register, surfacing a translated error to the caller."""
        try:
            await self._hub.async_write_setpoint(ent, value)
        except OSError as err:  # ConnectionError from the hub is an OSError
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_setpoint_failed",
                translation_placeholders={"entity_id": self.entity_id},
            ) from err
