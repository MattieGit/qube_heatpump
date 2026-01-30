"""Number platform for Qube Heat Pump setpoints."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import QubeConfigEntry
    from .hub import EntityDef, QubeHub


# Default min/max for temperature setpoints
DEFAULT_MIN_TEMP = 20.0
DEFAULT_MAX_TEMP = 65.0
DEFAULT_STEP = 0.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube number entities for setpoints."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"
    apply_label = data.apply_label_in_name
    multi_device = data.multi_device

    entities: list[NumberEntity] = []
    for ent in hub.entities:
        if ent.platform != "sensor":
            continue
        if not ent.writable:
            continue
        # Only create number entities for temperature setpoints
        if ent.unit_of_measurement not in ("°C", "C"):
            continue

        entities.append(
            QubeSetpointNumber(
                coordinator,
                hub,
                apply_label,
                multi_device,
                version,
                ent,
            )
        )

    async_add_entities(entities)


class QubeSetpointNumber(CoordinatorEntity, NumberEntity):
    """Number entity for Qube setpoints."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: Any,
        hub: QubeHub,
        show_label: bool,
        multi_device: bool,
        version: str,
        ent: EntityDef,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._ent = ent
        self._hub = hub
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version

        # Set name from translation or entity name
        if ent.translation_key:
            manual_name = hub.get_friendly_name("number", ent.translation_key)
            if manual_name:
                self._attr_name = manual_name
                self._attr_has_entity_name = False
            else:
                self._attr_translation_key = ent.translation_key
                self._attr_has_entity_name = True
        else:
            self._attr_name = str(ent.name)

        # Unique ID
        if ent.unique_id:
            base_uid = f"{ent.unique_id}_setpoint"
            self._attr_unique_id = (
                f"{base_uid}_{hub.entry_id}" if multi_device else base_uid
            )
        else:
            suffix = f"{ent.input_type or 'holding'}_{ent.address}".lower()
            base_uid = f"qube_setpoint_{suffix}"
            self._attr_unique_id = (
                f"{base_uid}_{hub.entry_id}" if multi_device else base_uid
            )

        # Suggested object ID
        vendor_id = ent.vendor_id
        if vendor_id:
            candidate = f"{vendor_id}_setpoint"
            if self._show_label:
                candidate = f"{self._label}_{candidate}"
            self._attr_suggested_object_id = _slugify(candidate)

        # Number configuration
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_native_min_value = ent.min_value or DEFAULT_MIN_TEMP
        self._attr_native_max_value = DEFAULT_MAX_TEMP
        self._attr_native_step = DEFAULT_STEP
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=(self._hub.label or "Qube Heatpump"),
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        key = (
            self._ent.unique_id
            or f"sensor_{self._ent.input_type or self._ent.write_type}_{self._ent.address}"
        )
        val = self.coordinator.data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the setpoint value."""
        await self._hub.async_connect()
        await self._hub.async_write_setpoint(self._ent, value)
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """Handle entity addition."""
        await super().async_added_to_hass()
        desired = self._ent.vendor_id
        if desired:
            desired = f"{desired}_setpoint"
            if self._show_label and not str(desired).startswith(f"{self._label}_"):
                desired = f"{self._label}_{desired}"
            await _async_ensure_entity_id(self.hass, self.entity_id, _slugify(desired))


async def _async_ensure_entity_id(
    hass: HomeAssistant, entity_id: str, desired_obj: str | None
) -> None:
    """Ensure the entity has the desired object ID."""
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
    with contextlib.suppress(Exception):
        registry.async_update_entity(current.entity_id, new_entity_id=desired_eid)


def _slugify(text: str) -> str:
    """Make text safe for use as an ID."""
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()
