from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    show_label = bool(data.get("show_label_in_name", False))

    async_add_entities([
        QubeReloadButton(coordinator, hub, entry.entry_id, show_label),
        QubeInfoButton(coordinator, hub, show_label),
        QubeMigrateIdsButton(coordinator, hub, entry.entry_id, show_label),
    ])


class QubeReloadButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub, entry_id: str, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        label = hub.label or "qube1"
        self._attr_name = f"Reload ({label})" if show_label else "Reload"
        self._attr_unique_id = f"qube_reload_{hub.host}_{hub.unit}"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
        )

    async def async_press(self) -> None:
        await self.hass.config_entries.async_reload(self._entry_id)


class QubeInfoButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        label = hub.label or "qube1"
        self._attr_name = f"Qube info ({label})" if show_label else "Qube info"
        self._attr_unique_id = f"qube_info_{hub.host}_{hub.unit}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
        )

    async def async_press(self) -> None:
        # Build a short info message
        hub = self._hub
        sensors = sum(1 for e in hub.entities if e.platform == "sensor")
        bsens = sum(1 for e in hub.entities if e.platform == "binary_sensor")
        switches = sum(1 for e in hub.entities if e.platform == "switch")
        # Try to resolve integration version
        version = "unknown"
        try:
            integ = await async_get_loaded_integration(self.hass, DOMAIN)
            if integ and getattr(integ, "version", None):
                version = integ.version
        except Exception:
            pass
        msg = (
            f"Label: {hub.label}\n"
            f"Host: {hub.host}\n"
            f"Unit/Slave ID: {hub.unit}\n"
            f"Version: {version}\n"
            f"Errors: connect={hub.err_connect}, read={hub.err_read}\n"
            f"Entities: sensors={sensors}, binary_sensors={bsens}, switches={switches}\n\n"
            "Tips:\n- Use Reload to refresh immediately.\n"
        )
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {"message": msg, "title": "Qube info"},
            blocking=False,
        )


class QubeMigrateIdsButton(CoordinatorEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, hub, entry_id: str, show_label: bool) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry_id = entry_id
        label = hub.label or "qube1"
        self._attr_name = f"Migrate IDs ({label})" if show_label else "Migrate IDs"
        self._attr_unique_id = f"qube_migrate_{hub.host}_{hub.unit}"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
        )

    async def async_press(self) -> None:
        # Invoke migration service with label suffix enforced
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "migrate_registry",
                {"prefer_vendor_only": False, "enforce_label_suffix": True, "label": self._hub.label, "dry_run": False},
                blocking=True,
            )
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {"message": "Migration done (see logs for details).", "title": "Qube migrate IDs"},
                blocking=False,
            )
        except Exception as exc:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {"message": f"Migration failed: {exc}", "title": "Qube migrate IDs"},
                blocking=False,
            )
