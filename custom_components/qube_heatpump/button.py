from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_loaded_integration, async_get_integration
from pathlib import Path
import json

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    show_label = bool(data.get("show_label_in_name", False))

    async_add_entities([
        QubeReloadButton(coordinator, hub, entry.entry_id, show_label),
    ])


class QubeReloadButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub, entry_id: str, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        label = hub.label or "qube1"
        self._attr_name = f"Reload ({label})" if show_label else "Reload"
        self._attr_unique_id = f"qube_reload_{label}"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=_resolve_integration_version(),
        )

    async def async_press(self) -> None:
        await self.hass.config_entries.async_reload(self._entry_id)


# QubeInfoButton removed in favor of diagnostic info sensor


def _resolve_integration_version() -> str:
    """Resolve integration version from manifest for displaying in Device info."""
    try:
        manifest = Path(__file__).resolve().parent / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            vers = data.get("version")
            if vers:
                return str(vers)
    except Exception:
        pass
    return "unknown"
