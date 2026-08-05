"""Button entities for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import QubeEntity

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

    async_add_entities(
        [
            QubeReloadButton(
                coordinator,
                hub,
                entry.entry_id,
                version,
            ),
        ]
    )


class QubeReloadButton(QubeEntity, ButtonEntity):
    """Button to reload the Qube integration."""

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        entry_id: str,
        version: str,
    ) -> None:
        """Initialize the reload button."""
        super().__init__(coordinator, hub, version)
        self._entry_id = entry_id
        self._attr_translation_key = "qube_reload"
        self.entity_id = f"button.{self._label}_reload"

        # Always scope unique_id per device for stability
        self._attr_unique_id = self._scoped_uid("qube_reload")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Handle the button press to reload the config entry."""
        await self.hass.config_entries.async_reload(self._entry_id)
