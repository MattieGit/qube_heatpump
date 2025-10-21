from __future__ import annotations

from typing import Callable, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, TARIFF_OPTIONS
from .sensor import TariffEnergyTracker, _append_label, _binary_unique_id, _energy_unique_id


class QubeEnergyTariffSelect(CoordinatorEntity, RestoreEntity, SelectEntity):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        hub,
        tracker: TariffEnergyTracker,
        show_label: bool,
        multi_device: bool,
        version: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._tracker = tracker
        self._label = hub.label or "qube1"
        self._show_label = bool(show_label)
        self._multi_device = bool(multi_device)
        self._version = version
        base_unique = "qube_energy_tariff_select"
        self._attr_unique_id = _append_label(base_unique, hub.label, multi_device)
        self._attr_name = "Tarief elektrisch verbruik"
        suggested = "heatpump_energy"
        if self._show_label:
            suggested = f"{suggested}_{self._label}"
        self._attr_suggested_object_id = suggested
        self._attr_options = list(TARIFF_OPTIONS)
        self._unsub_tracker: Optional[Callable[[], None]] = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self.options:
            self._tracker.set_manual_tariff(last_state.state)
        if self._unsub_tracker is None:
            self._unsub_tracker = self._tracker.register_listener(self._handle_tracker_event)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub.host}:{self._hub.unit}")},
            name=self._hub.label or "Qube Heatpump",
            manufacturer="Qube",
            model="Heatpump",
            sw_version=self._version,
        )

    @property
    def current_option(self) -> str:
        return self._tracker.current_tariff

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            return
        self._tracker.set_manual_tariff(option)
        self.async_write_ha_state()

    def _handle_tracker_event(self) -> None:
        if self.hass is None:
            return
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    tracker: TariffEnergyTracker | None = data.get("tariff_tracker")
    hub = data["hub"]
    coordinator = data["coordinator"]
    apply_label = data.get("apply_label_in_name", False)
    multi_device = data.get("multi_device", False)
    version = data.get("version", "unknown")

    if tracker is None:
        tracker = TariffEnergyTracker(
            base_key=_energy_unique_id(data.get("label"), multi_device),
            binary_key=_binary_unique_id(data.get("label"), multi_device),
            tariffs=list(TARIFF_OPTIONS),
        )
        data["tariff_tracker"] = tracker

    async_add_entities(
        [
            QubeEnergyTariffSelect(
                coordinator,
                hub,
                tracker,
                show_label=apply_label,
                multi_device=multi_device,
                version=version,
            )
        ]
    )
