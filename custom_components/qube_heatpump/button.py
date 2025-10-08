from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    version = data.get("version", "unknown")
    apply_label = bool(data.get("apply_label_in_name", False))
    multi_device = bool(data.get("multi_device", False))

    async_add_entities([
        QubeReloadButton(
            coordinator,
            hub,
            entry.entry_id,
            apply_label or multi_device,
            multi_device,
            version,
        ),
    ])


async def _async_ensure_entity_id(hass: HomeAssistant, entity_id: str, desired_obj: str | None) -> None:
    if not desired_obj:
        return
    registry = er.async_get(hass)
    current = registry.async_get(entity_id)
    if not current:
        return
    desired_eid = f"{current.domain}.{desired_obj}"
    if current.entity_id == desired_eid:
        return
    if registry.async_get(desired_eid):
        return
    try:
        registry.async_update_entity(current.entity_id, new_entity_id=desired_eid)
    except Exception:
        return


class QubeReloadButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub,
        entry_id: str,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        self._multi_device = bool(multi_device)
        self._version = version
        label = hub.label or "qube1"
        self._attr_name = f"Reload ({label})" if show_label else "Reload"
        self._attr_unique_id = f"qube_reload_{label}" if self._multi_device else "qube_reload"
        self._attr_entity_category = EntityCategory.CONFIG
        # Suggest a stable object_id reflecting multi-device label when needed
        try:
            from .sensor import _slugify  # reuse helper

            self._attr_suggested_object_id = (
                _slugify(f"qube_reload_{label}") if self._multi_device or show_label else "qube_reload"
            )
        except Exception:
            pass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    async def async_press(self) -> None:
        await self.hass.config_entries.async_reload(self._entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        label = self._hub.label or "qube1"
        desired_obj = _slugify_local(f"qube_reload_{label}" if self._multi_device else "qube_reload")
        await _async_ensure_entity_id(self.hass, self.entity_id, desired_obj)


def _slugify_local(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()
