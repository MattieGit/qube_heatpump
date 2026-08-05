"""Base entity for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from .hub import QubeHub


class QubeEntity(CoordinatorEntity):
    """Common base for Qube coordinator entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, hub: QubeHub, version: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._hub = hub
        self._version = str(version) if version else "unknown"
        self._label = hub.label
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{hub.host}:{hub.unit}")},
            name=hub.device_name,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self._version,
        )

    def _scoped_uid(self, base: str) -> str:
        """Scope a unique_id with host_unit prefix for multi-device stability."""
        return f"{self._hub.host}_{self._hub.unit}_{base}"
