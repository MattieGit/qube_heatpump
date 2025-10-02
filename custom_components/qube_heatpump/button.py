from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    version = data.get("version", "unknown")
    # For parity with Diagnostics sensors: show label in name when multiple
    # devices exist (force_label_in_diag), or if user opted in.
    show_label_diag = bool(data.get("force_label_in_diag", False)) or bool(
        data.get("show_label_in_name", False)
    )

    async_add_entities([
        QubeReloadButton(
            coordinator,
            hub,
            entry.entry_id,
            show_label_diag,
            version,
            force_label=bool(data.get("force_label_in_diag", False)),
        ),
    ])


class QubeReloadButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub,
        entry_id: str,
        show_label: bool,
        version: str,
        force_label: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        self._force_label = bool(force_label)
        self._version = version
        label = hub.label or "qube1"
        self._attr_name = f"Reload ({label})" if show_label else "Reload"
        # Unique_id: include label suffix only when multiple devices exist.
        self._attr_unique_id = f"qube_reload_{label}" if self._force_label else "qube_reload"
        self._attr_entity_category = EntityCategory.CONFIG
        # Suggest a stable object_id reflecting multi-device label when needed
        try:
            from .sensor import _slugify  # reuse helper

            self._attr_suggested_object_id = (
                _slugify(f"qube_reload_{label}") if self._force_label else "qube_reload"
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
        # Align entity_id with desired label form in multi-device setups.
        await super().async_added_to_hass()
        if not self._force_label:
            return
        try:
            from homeassistant.helpers import entity_registry as er
            from .sensor import _slugify

            registry = er.async_get(self.hass)
            current = registry.async_get(self.entity_id)
            if not current:
                return
            desired_obj = _slugify(f"qube_reload_{self._hub.label}")
            desired_eid = f"button.{desired_obj}"
            if current.entity_id != desired_eid and registry.async_get(desired_eid) is None:
                try:
                    registry.async_update_entity(self.entity_id, new_entity_id=desired_eid)
                except Exception:
                    pass
        except Exception:
            pass
