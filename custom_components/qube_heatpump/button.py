"""Button entities for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import QubeHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qube reload button."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"
    # show_label is no longer used (entity IDs are auto-generated from device name)
    show_label = False
    multi_device = data.multi_device

    async_add_entities(
        [
            QubeReloadButton(
                coordinator,
                hub,
                entry.entry_id,
                show_label,
                multi_device,
                version,
            ),
        ]
    )


class QubeReloadButton(CoordinatorEntity, ButtonEntity):
    """Button to reload the Qube integration."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        entry_id: str,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        """Initialize the reload button."""
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        self._multi_device = bool(multi_device)
        self._version = version
        label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._attr_translation_key = "qube_reload"
        self._attr_suggested_object_id = "reload"

        # Stable unique ID - scope per device in multi-device setups
        self._attr_unique_id = (
            f"{self._hub.host}_{self._hub.unit}_qube_reload"
            if self._multi_device
            else "qube_reload"
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.device_name,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self._version,
        )

    async def async_press(self) -> None:
        """Handle the button press to reload the config entry."""
        await self.hass.config_entries.async_reload(self._entry_id)
