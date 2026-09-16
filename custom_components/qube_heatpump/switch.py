"""Switch platform for Qube Heat Pump."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import CONF_DHW_SCHEDULE_ENABLED, DOMAIN
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

# The SG Ready coils are exposed through the select entity instead
SGREADY_VENDOR_IDS = frozenset({"bms_sgready_a", "bms_sgready_b"})

# Coils the controller keeps on after an acknowledged turn-off while a request
# is still pending (they clear by themselves when the run completes). These
# switches expose a ``pending_request`` attribute instead of pretending the
# write took effect.
PENDING_STATE_SWITCHES = frozenset({"tapw_timeprogram_bms_forced"})

# Switches that should appear in Controls (no entity_category) instead of Configuration
CONTROL_SWITCHES = frozenset(
    {
        "modbus_demand",
        "tapw_timeprogram_bms_forced",
        "bms_summerwinter",
        "antilegionella_frcstart_ant",
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Qube switches."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version

    entities: list[SwitchEntity] = [
        QubeSwitch(coordinator, hub, ent, version)
        for ent in hub.entities
        if ent.platform == "switch" and ent.vendor_id not in SGREADY_VENDOR_IDS
    ]
    entities.append(QubeDhwScheduleEnabledSwitch(coordinator, hub, entry, version))
    async_add_entities(entities)

    # Cleanup deprecated SG Ready switch entities from releases that created
    # them (both the old unscoped and the scoped unique_id formats).
    registry = er.async_get(hass)
    for base in SGREADY_VENDOR_IDS:
        for unique_id in (base, f"{hub.host}_{hub.unit}_{base}"):
            if entity_id := registry.async_get_entity_id("switch", DOMAIN, unique_id):
                registry.async_remove(entity_id)


class QubeSwitch(QubeEntity, SwitchEntity):
    """Qube switch entity backed by a writable coil."""

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        ent: EntityDef,
        version: str = "unknown",
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, hub, version)
        self._ent = ent
        self._key = entity_data_key(ent)
        # True after an acknowledged turn-off until the coil actually reads off
        self._turn_off_requested = False
        # Control switches go in Controls section, others in Configuration
        if ent.vendor_id not in CONTROL_SWITCHES:
            self._attr_entity_category = EntityCategory.CONFIG
        # vendor_id gives stable, predictable entity IDs
        self.entity_id = f"switch.{self._label}_{ent.vendor_id}"
        self._attr_translation_key = ent.translation_key
        # Always scoped per device (host_unit prefix) for multi-device stability
        self._attr_unique_id = self._scoped_uid(self._key)

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        val = self.coordinator.data.get(self._key)
        return None if val is None else bool(val)

    @property
    def pending_request(self) -> bool:
        """Return True if a turn-off was acknowledged but the coil still reads on."""
        return self._turn_off_requested and self.is_on is True

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the pending state for coils the controller may hold on."""
        if self._ent.vendor_id not in PENDING_STATE_SWITCHES:
            return None
        return {"pending_request": self.pending_request}

    def _handle_coordinator_update(self) -> None:
        """Forget the pending turn-off once the coil actually reads off."""
        if self._turn_off_requested and self.is_on is False:
            self._turn_off_requested = False
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._turn_off_requested = False
        await self._async_connect()
        await self._async_write_switch(self._ent, True)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_connect()
        await self._async_write_switch(self._ent, False)
        self._turn_off_requested = self._ent.vendor_id in PENDING_STATE_SWITCHES
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
        if self.pending_request:
            _LOGGER.info(
                "%s: turn-off acknowledged but the coil is still on; the controller "
                "keeps it on while a DHW request is pending and clears it itself",
                self.entity_id,
            )


class QubeDhwScheduleEnabledSwitch(QubeEntity, SwitchEntity):
    """Runtime toggle for the DHW schedule option.

    Writes ``dhw_schedule_enabled`` into the config-entry options; the entry's
    update listener then reloads the integration, which registers or removes
    the time-change callbacks. No Modbus traffic is involved.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-clock"
    _attr_translation_key = "dhw_schedule_enabled"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        entry: QubeConfigEntry,
        version: str = "unknown",
    ) -> None:
        """Initialize the schedule toggle."""
        super().__init__(coordinator, hub, version)
        self._entry = entry
        self.entity_id = f"switch.{self._label}_dhw_schedule_enabled"
        self._attr_unique_id = self._scoped_uid("dhw_schedule_enabled")

    @property
    def is_on(self) -> bool:
        """Return True if the schedule option is enabled."""
        return bool(self._entry.options.get(CONF_DHW_SCHEDULE_ENABLED, False))

    def _set_enabled(self, value: bool) -> None:
        if self.is_on == value:
            return
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_DHW_SCHEDULE_ENABLED: value},
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the DHW schedule (triggers a reload)."""
        self._set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the DHW schedule (triggers a reload)."""
        self._set_enabled(False)
