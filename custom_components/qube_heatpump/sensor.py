"""Sensor platform for Qube Heat Pump."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from python_qube_heatpump import StatusCode, resolve_status

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.loader import IntegrationNotFound, async_get_integration
from homeassistant.util import dt as dt_util

from .const import DOMAIN, TARIFF_OPTIONS
from .entity import QubeEntity
from .helpers import entity_data_key as _entity_key

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from . import QubeConfigEntry
    from .coordinator import QubeCoordinator
    from .entity_defs import EntityDef
    from .hub import QubeHub

# Sensors that should clamp values to minimum 0 (percentages, flow rates)
CLAMP_TO_ZERO_KEYS = frozenset({"dhw_regreq", "flow", "flow_rate"})

# Value indicating room sensor is not installed (-999)
ROOM_SENSOR_NOT_INSTALLED = -999

# COP sensor throttling - reduce update frequency since daily/monthly SCOP is more useful
COP_THROTTLE_KEYS = frozenset({"cop_calc"})
COP_THROTTLE_SECONDS = 30  # Minimum seconds between state updates
COP_THROTTLE_THRESHOLD = 0.2  # Force update if value changes by more than this

# Library keys that alias another register under a second name (same address,
# same friendly name). They stay in the registry for backwards compatibility
# but are disabled by default so users do not see every value twice.
ALIAS_KEYS = frozenset(
    {
        "flow_rate",  # flow (18)
        "setpoint_room_heat_day",  # thermostat_heatsetp_day (27)
        "setpoint_room_heat_night",  # thermostat_heatsetp_night (29)
        "setpoint_room_cool_day",  # thermostat_coolsetp_day (31)
        "setpoint_room_cool_night",  # thermostat_coolsetp_night (33)
        "setpoint_dhw",  # tapw_timeprogram_dhwsetp_nolinq (173)
    }
)
# temp_room: most users use the LinQ thermostat instead.
# cop_calc: the daily/monthly SCOP averages are more useful than real-time COP.
DISABLED_BY_DEFAULT_KEYS = ALIAS_KEYS | {"temp_room"} | COP_THROTTLE_KEYS

# Coordinator data keys (unscoped library keys) read by the derived sensors
STATUS_CODE_KEY = "status_code"
ANTILEG_KEY = "req_antileg_1"
THREEWAY_VALVE_KEY = "dout_threewayvlv_val"
FOURWAY_VALVE_KEY = "dout_fourwayvlv_val"
ENERGY_DATA_KEY = "energy_total_electric"
THERMIC_DATA_KEY = "energy_total_thermic"

STATUS_OPTIONS = [status.value for status in StatusCode]
THREEWAY_VALVE_OPTIONS = ["dhw", "ch"]
FOURWAY_VALVE_OPTIONS = ["heating", "cooling"]
COMPUTED_OPTIONS = {
    "status": STATUS_OPTIONS,
    "drieweg": THREEWAY_VALVE_OPTIONS,
    "vierweg": FOURWAY_VALVE_OPTIONS,
}
# (translation_key, unique_suffix, kind, source vendor_id)
COMPUTED_SENSORS = (
    ("status_heatpump", "status_full", "status", STATUS_CODE_KEY),
    ("threeway_valve_status", "driewegklep_dhw_cv", "drieweg", THREEWAY_VALVE_KEY),
    (
        "fourway_valve_status",
        "vierwegklep_verwarmen_koelen",
        "vierweg",
        FOURWAY_VALVE_KEY,
    ),
)

STANDBY_POWER_WATTS = 17.0
STANDBY_POWER_UNIQUE_BASE = "power_standby"
STANDBY_ENERGY_UNIQUE_BASE = "energy_standby"
TOTAL_ENERGY_UNIQUE_BASE = "energy_total_incl_standby"

SCOP_MAX_EXPECTED = 10.0
# Minimum electric consumption in a cycle before a SCOP is reported; a few
# Wh right after a cycle start would otherwise produce wild ratios.
SCOP_MIN_ELECTRIC_KWH = 0.1


def _find_entity(hub: QubeHub, vendor_id: str) -> EntityDef | None:
    """Return the hub entity definition with the given library key."""
    return next((ent for ent in hub.entities if ent.vendor_id == vendor_id), None)


# Writes go through the shared hub; no per-platform throttling needed.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qube sensors."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    version = data.version or "unknown"
    initial_data = coordinator.data or {}

    entities: list[SensorEntity] = [
        QubeIPAddressSensor(coordinator, hub, version),
        QubeDhwScheduleNextStartSensor(coordinator, hub, entry, version),
        QubeMetricSensor(coordinator, hub, version, kind="errors_connect"),
        QubeMetricSensor(coordinator, hub, version, kind="errors_read"),
        QubeInfoSensor(coordinator, hub, version),
        QubeStandbyPowerSensor(coordinator, hub, version),
    ]

    entities.extend(
        QubeSensor(coordinator, hub, version, ent)
        for ent in hub.entities
        if ent.platform == "sensor"
    )

    # Human-readable heat pump status and valve positions
    for translation_key, unique_suffix, kind, vendor_id in COMPUTED_SENSORS:
        if (source := _find_entity(hub, vendor_id)) is not None:
            entities.append(
                QubeComputedSensor(
                    coordinator,
                    hub,
                    version,
                    translation_key=translation_key,
                    unique_suffix=unique_suffix,
                    kind=kind,
                    source=source,
                )
            )

    standby_energy = QubeStandbyEnergySensor(coordinator, hub, version)
    entities.append(standby_energy)
    entities.append(
        QubeTotalEnergyIncludingStandbySensor(coordinator, hub, version, standby_energy)
    )

    def _make_tracker(base_key: str, reset_period: str) -> TariffEnergyTracker:
        tracker = TariffEnergyTracker(
            base_key=base_key,
            binary_key=THREEWAY_VALVE_KEY,
            tariffs=list(TARIFF_OPTIONS),
            reset_period=reset_period,
        )
        tracker.set_initial_total(initial_data.get(base_key))
        return tracker

    monthly_electric = _make_tracker(ENERGY_DATA_KEY, "month")
    monthly_thermic = _make_tracker(THERMIC_DATA_KEY, "month")
    daily_electric = _make_tracker(ENERGY_DATA_KEY, "day")
    daily_thermic = _make_tracker(THERMIC_DATA_KEY, "day")

    # Per tracker: (tariff, translation_key, unique_base). Unique bases are
    # historical and must not change; a tariff sensor appends "_<tariff>".
    tariff_sensors: tuple[
        tuple[TariffEnergyTracker, tuple[tuple[str | None, str, str], ...]], ...
    ] = (
        (
            monthly_electric,
            (
                ("CH", "electric_consumption_ch_month", "qube_energy_tariff"),
                ("DHW", "electric_consumption_dhw_month", "qube_energy_tariff"),
            ),
        ),
        (
            monthly_thermic,
            (
                (None, "thermic_yield_month", "qube_thermic_energy_monthly"),
                ("CH", "thermic_yield_ch_month", "qube_thermic_energy_tariff"),
                ("DHW", "thermic_yield_dhw_month", "qube_thermic_energy_tariff"),
            ),
        ),
        (
            daily_electric,
            (
                (None, "electric_consumption_day", "qube_electric_energy_daily"),
                ("CH", "electric_consumption_ch_day", "qube_energy_tariff_daily"),
                ("DHW", "electric_consumption_dhw_day", "qube_energy_tariff_daily"),
            ),
        ),
        (
            daily_thermic,
            (
                (None, "thermic_yield_day", "qube_thermic_energy_daily"),
                ("CH", "thermic_yield_ch_day", "qube_thermic_tariff_daily"),
                ("DHW", "thermic_yield_dhw_day", "qube_thermic_tariff_daily"),
            ),
        ),
    )
    entities.extend(
        QubeTariffEnergySensor(
            coordinator,
            hub,
            version,
            tracker,
            tariff=tariff,
            translation_key=translation_key,
            unique_base=unique_base,
        )
        for tracker, rows in tariff_sensors
        for tariff, translation_key, unique_base in rows
    )

    # Per (electric, thermic) tracker pair: (scope, translation_key, unique_base)
    scop_sensors = (
        (
            monthly_electric,
            monthly_thermic,
            (
                ("total", "scop_month", "qube_scop_monthly"),
                ("CH", "scop_ch_month", "qube_scop_ch_monthly"),
                ("DHW", "scop_dhw_month", "qube_scop_dhw_monthly"),
            ),
        ),
        (
            daily_electric,
            daily_thermic,
            (
                ("total", "scop_day", "qube_scop_daily"),
                ("CH", "scop_ch_day", "qube_scop_ch_daily"),
                ("DHW", "scop_dhw_day", "qube_scop_dhw_daily"),
            ),
        ),
    )
    entities.extend(
        QubeSCOPSensor(
            coordinator,
            hub,
            electric_tracker=electric,
            thermic_tracker=thermic,
            scope=scope,
            translation_key=translation_key,
            unique_base=unique_base,
            version=version,
        )
        for electric, thermic, rows in scop_sensors
        for scope, translation_key, unique_base in rows
    )

    async_add_entities(entities)


def _sensor_description(ent: EntityDef) -> SensorEntityDescription:
    """Build the entity description for a library-backed register sensor.

    ``device_class``/``state_class`` on the definition may be plain strings or
    the Home Assistant enum members; both are accepted.
    """
    return SensorEntityDescription(
        key=ent.vendor_id or "",
        translation_key=ent.translation_key,
        native_unit_of_measurement=ent.unit_of_measurement,
        device_class=SensorDeviceClass(ent.device_class) if ent.device_class else None,
        state_class=SensorStateClass(ent.state_class) if ent.state_class else None,
        suggested_display_precision=ent.precision,
        entity_registry_enabled_default=ent.vendor_id not in DISABLED_BY_DEFAULT_KEYS,
    )


class QubeSensor(QubeEntity, SensorEntity):
    """Sensor backed by a single Modbus register from the library."""

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        ent: EntityDef,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, hub, version)
        self._ent = ent
        self._key = ent.vendor_id
        self.entity_description = _sensor_description(ent)
        # vendor_id gives stable, predictable entity IDs (see CLAUDE.md);
        # unique_id is scoped per device for multi-device stability.
        self.entity_id = f"sensor.{self._label}_{ent.vendor_id}"
        self._attr_unique_id = self._scoped_uid(ent.unique_id or "")

        # Throttling for COP sensors to reduce update frequency
        self._is_cop_sensor = self._key in COP_THROTTLE_KEYS
        self._throttle_last_value: float | None = None
        self._throttle_last_update: datetime | None = None
        self._cop_display_value: StateType = (
            self._compute_throttled_value() if self._is_cop_sensor else None
        )

    def _compute_value(self) -> StateType:
        """Compute the sensor's display value (before any COP throttling).

        The coordinator already rounds values to the entity precision.
        """
        value = self.coordinator.data.get(_entity_key(self._ent))
        if value is None:
            return None

        # Handle temp_room showing -999 when sensor not installed
        if self._key == "temp_room" and value == ROOM_SENSOR_NOT_INSTALLED:
            return None

        # Clamp values that should never be negative (percentages, flow rates).
        # max() also normalises -0.0, which equals 0 but displays as negative.
        if self._key in CLAMP_TO_ZERO_KEYS and isinstance(value, (int, float)):
            return max(0.0, float(value))

        return cast("StateType", value)

    def _compute_throttled_value(self) -> StateType:
        """Compute the COP display value, throttling frequent small changes.

        Only updates the cached value if enough time passed or the value
        changed significantly. Must be called at most once per coordinator
        update cycle (from `_handle_coordinator_update`) since it mutates the
        throttle cache.
        """
        value = self._compute_value()
        if value is None:
            return None

        now = dt_util.utcnow()
        try:
            current_value = float(value)
        except (TypeError, ValueError):
            return value

        if (
            self._throttle_last_value is not None
            and self._throttle_last_update is not None
        ):
            time_diff = (now - self._throttle_last_update).total_seconds()
            value_diff = abs(current_value - self._throttle_last_value)
            # Return cached value if not enough time passed and value stable
            if time_diff < COP_THROTTLE_SECONDS and value_diff < COP_THROTTLE_THRESHOLD:
                return self._throttle_last_value

        self._throttle_last_value = current_value
        self._throttle_last_update = now
        return current_value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._is_cop_sensor:
            self._cop_display_value = self._compute_throttled_value()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return native value."""
        if self._is_cop_sensor:
            return self._cop_display_value
        return self._compute_value()


class QubeInfoSensor(QubeEntity, SensorEntity):
    """Diagnostic info sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "info"
    _attr_native_value = "ok"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
    ) -> None:
        """Initialize info sensor."""
        super().__init__(coordinator, hub, version)
        self._integration_version: str | None = None
        self.entity_id = f"sensor.{self._label}_info"
        self._attr_unique_id = self._scoped_uid("info_sensor")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        hub = self._hub
        return {
            "firmware_version": self._version,
            "integration_version": self._integration_version or "unknown",
            "label": hub.label,
            "host": hub.host,
            "ip_address": hub.resolved_ip,
            "unit_id": hub.unit,
            "errors_connect": hub.err_connect,
            "errors_read": hub.err_read,
        }

    async def async_added_to_hass(self) -> None:
        """Look up the integration version from the manifest."""
        await super().async_added_to_hass()
        try:
            integration = await async_get_integration(self.hass, DOMAIN)
        except IntegrationNotFound:
            return
        if integration.version:
            self._integration_version = str(integration.version)
            self.async_write_ha_state()


class QubeDhwScheduleNextStartSensor(QubeEntity, SensorEntity):
    """Timestamp of the next scheduled DHW start; unknown while the schedule is off."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "dhw_schedule_next_start"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        entry: QubeConfigEntry,
        version: str,
    ) -> None:
        """Initialize the next-start sensor."""
        super().__init__(coordinator, hub, version)
        self._entry = entry
        self.entity_id = f"sensor.{self._label}_dhw_schedule_next_start"
        self._attr_unique_id = self._scoped_uid("dhw_schedule_next_start")

    async def async_added_to_hass(self) -> None:
        """Subscribe to scheduler state changes."""
        await super().async_added_to_hass()
        state = self._entry.runtime_data.dhw_schedule
        if state is not None:
            self.async_on_remove(state.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        """Return the next start, or None when the schedule is disabled."""
        state = self._entry.runtime_data.dhw_schedule
        if state is None or not state.enabled:
            return None
        return state.next_start


class QubeIPAddressSensor(QubeEntity, SensorEntity):
    """Resolved IP address of the heat pump."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "ip_address"

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
    ) -> None:
        """Initialize IP sensor."""
        super().__init__(coordinator, hub, version)
        self.entity_id = f"sensor.{self._label}_ip_address"
        self._attr_unique_id = self._scoped_uid("ip_address")

    @property
    def native_value(self) -> str | None:
        """Return IP address."""
        return self._hub.resolved_ip or self._hub.host


class QubeMetricSensor(QubeEntity, SensorEntity):
    """Error counter (connect or read failures since the hub was created)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        kind: str,
    ) -> None:
        """Initialize metric sensor."""
        super().__init__(coordinator, hub, version)
        self._kind = kind
        self._attr_translation_key = f"metric_{kind}"
        self.entity_id = f"sensor.{self._label}_metric_{kind}"
        self._attr_unique_id = self._scoped_uid(f"metric_{kind}")

    @property
    def native_value(self) -> int:
        """Return the counter value."""
        if self._kind == "errors_connect":
            return self._hub.err_connect
        return self._hub.err_read


class QubeStandbyPowerSensor(QubeEntity, SensorEntity):
    """Constant standby power draw of the controller."""

    _attr_translation_key = "standby_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_value = STANDBY_POWER_WATTS

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
    ) -> None:
        """Initialize standby power sensor."""
        super().__init__(coordinator, hub, version)
        self.entity_id = f"sensor.{self._label}_standby_power"
        self._attr_unique_id = self._scoped_uid(STANDBY_POWER_UNIQUE_BASE)


class QubeStandbyEnergySensor(QubeEntity, RestoreSensor):
    """Standby energy, integrated from the constant standby power."""

    _attr_translation_key = "standby_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
    ) -> None:
        """Initialize standby energy sensor."""
        super().__init__(coordinator, hub, version)
        self._energy_kwh: float = 0.0
        self._last_update: datetime | None = None
        self.entity_id = f"sensor.{self._label}_standby_energy"
        self._attr_unique_id = self._scoped_uid(STANDBY_ENERGY_UNIQUE_BASE)

    async def async_added_to_hass(self) -> None:
        """Resume integrating from the last persisted value."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "", "unknown", "unavailable"):
            try:
                self._energy_kwh = float(last_state.state)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0
            self._last_update = last_state.last_changed
        if self._last_update is None:
            self._last_update = dt_util.utcnow()

    @property
    def native_value(self) -> float:
        """Return value."""
        return round(self._energy_kwh, 3)

    def _integrate(self) -> None:
        now = dt_util.utcnow()
        if self._last_update is None:
            self._last_update = now
            return
        elapsed = (now - self._last_update).total_seconds()
        if elapsed <= 0:
            return
        self._last_update = now
        self._energy_kwh += (STANDBY_POWER_WATTS / 1000.0) * (elapsed / 3600.0)

    def _handle_coordinator_update(self) -> None:
        self._integrate()
        super()._handle_coordinator_update()

    def current_energy(self) -> float:
        """Return the standby energy integrated up to now."""
        self._integrate()
        return self._energy_kwh


class QubeTotalEnergyIncludingStandbySensor(QubeEntity, SensorEntity):
    """Electric energy total from the meter plus the integrated standby energy."""

    _attr_translation_key = "total_energy_incl_standby"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        standby_sensor: QubeStandbyEnergySensor,
    ) -> None:
        """Initialize total energy sensor."""
        super().__init__(coordinator, hub, version)
        self._standby_sensor = standby_sensor
        self.entity_id = f"sensor.{self._label}_total_energy_incl_standby"
        self._attr_unique_id = self._scoped_uid(TOTAL_ENERGY_UNIQUE_BASE)

    @property
    def native_value(self) -> float | None:
        """Return the meter total plus standby energy."""
        base = self.coordinator.data.get(ENERGY_DATA_KEY)
        if not isinstance(base, (int, float)):
            return None
        return round(base + self._standby_sensor.current_energy(), 3)


class QubeComputedSensor(QubeEntity, SensorEntity):
    """Human-readable state derived from a raw register (status code or valve)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        *,
        translation_key: str,
        unique_suffix: str,
        kind: str,
        source: EntityDef,
    ) -> None:
        """Initialize computed sensor."""
        super().__init__(coordinator, hub, version)
        self._kind = kind
        self._source_key = _entity_key(source)
        self._attr_translation_key = translation_key
        self._attr_options = COMPUTED_OPTIONS[kind]
        self.entity_id = f"sensor.{self._label}_{translation_key}"
        self._attr_unique_id = self._scoped_uid(f"qube_{unique_suffix}")

    @property
    def native_value(self) -> str | None:
        """Return native value."""
        value = self.coordinator.data.get(self._source_key)
        if value is None:
            return None
        if self._kind == "status":
            try:
                code = int(value)
            except (TypeError, ValueError):
                return None
            antileg = self.coordinator.data.get(ANTILEG_KEY)
            return resolve_status(code, antileg).value
        if self._kind == "drieweg":
            # Three-way valve: DHW (True) vs CH (False)
            return "dhw" if value else "ch"
        # Four-way valve: heating (True) vs cooling (False)
        return "heating" if value else "cooling"


def _start_of_month(dt_value: datetime) -> datetime:
    """Return 00:00 local time on the 1st of dt_value's local month, as UTC."""
    local = dt_util.as_local(dt_value)
    return dt_util.as_utc(
        local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )


def _start_of_day(dt_value: datetime) -> datetime:
    """Return 00:00 local time on dt_value's local date, as UTC."""
    local = dt_util.as_local(dt_value)
    return dt_util.as_utc(local.replace(hour=0, minute=0, second=0, microsecond=0))


class TariffEnergyTracker:
    """Track split energy totals for CH/DHW (Central Heating / Domestic Hot Water)."""

    def __init__(
        self,
        base_key: str,
        binary_key: str,
        tariffs: list[str],
        reset_period: str = "month",
    ) -> None:
        """Initialize tracker."""
        self.base_key = base_key
        self.binary_key = binary_key
        self.tariffs = list(tariffs)
        self._totals: dict[str, float] = dict.fromkeys(tariffs, 0.0)
        self._current_tariff: str = tariffs[0]
        self._last_total: float | None = None
        self._reset_period = reset_period
        self._last_reset: datetime = self._cycle_start(dt_util.utcnow())
        self._last_token: datetime | None = None

    @property
    def current_tariff(self) -> str:
        """Return current tariff."""
        return self._current_tariff

    @property
    def last_reset(self) -> datetime:
        """Return last reset time."""
        return self._last_reset

    def restore_total(
        self, tariff: str, value: float, last_reset: datetime | None
    ) -> None:
        """Restore a tariff total persisted before a restart.

        ``last_reset`` is the cycle start the value was accumulated in. A value
        from an earlier cycle is discarded so that a restart across a day or
        month boundary starts the new cycle at zero.
        """
        if tariff not in self._totals:
            return
        if last_reset is not None:
            last_reset = dt_util.as_utc(last_reset)
            if last_reset < self._last_reset:
                return
            if last_reset > self._last_reset:
                self._last_reset = last_reset
        self._totals[tariff] = max(0.0, value)

    def set_initial_total(self, total: float | None) -> None:
        """Set initial total."""
        if total is None:
            return
        try:
            self._last_total = float(total)
        except (TypeError, ValueError):
            self._last_total = None

    def _cycle_start(self, dt_value: datetime) -> datetime:
        if self._reset_period == "day":
            return _start_of_day(dt_value)
        return _start_of_month(dt_value)

    def _reset_if_needed(self, reference: datetime) -> None:
        start = self._cycle_start(reference)
        if start > self._last_reset:
            self._last_reset = start
            for tariff in self._totals:
                self._totals[tariff] = 0.0

    def update(self, coordinator_data: dict[str, Any], token: datetime | None) -> None:
        """Update tracker with new data."""
        if (
            token is not None
            and self._last_token is not None
            and token <= self._last_token
        ):
            self._refresh_current_tariff(coordinator_data)
            return

        if token is not None:
            self._last_token = token

        # Roll the cycle over first, so an idle heat pump (no delta) still
        # starts the new day/month at zero.
        self._reset_if_needed(token or dt_util.utcnow())
        self._refresh_current_tariff(coordinator_data)

        base_val = coordinator_data.get(self.base_key)
        try:
            base_float = float(base_val) if base_val is not None else None
        except (TypeError, ValueError):
            base_float = None
        if base_float is None:
            return

        if self._last_total is None:
            self._last_total = base_float
            return

        delta = base_float - self._last_total
        self._last_total = base_float
        if delta > 0:
            self._totals[self._current_tariff] += delta

    def _refresh_current_tariff(self, coordinator_data: dict[str, Any]) -> None:
        state = coordinator_data.get(self.binary_key)
        if isinstance(state, bool):
            self._current_tariff = "DHW" if state else "CH"

    def get_total(self, tariff: str) -> float:
        """Get total for tariff."""
        return self._totals.get(tariff, 0.0)


class QubeTariffEnergySensor(QubeEntity, RestoreSensor):
    """Energy accumulated in the current day/month cycle, per tariff or in total."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        version: str,
        tracker: TariffEnergyTracker,
        *,
        tariff: str | None,
        translation_key: str,
        unique_base: str,
    ) -> None:
        """Initialize tariff sensor; ``tariff`` None sums all tariffs."""
        super().__init__(coordinator, hub, version)
        self._tracker = tracker
        self._tariff = tariff
        self._attr_translation_key = translation_key
        self.entity_id = f"sensor.{self._label}_{translation_key}"
        base = unique_base if tariff is None else f"{unique_base}_{tariff.lower()}"
        self._attr_unique_id = self._scoped_uid(base)

    async def async_added_to_hass(self) -> None:
        """Restore the per-tariff total into the shared tracker.

        Total sensors restore nothing: they sum the restored tariff values.
        """
        await super().async_added_to_hass()
        if self._tariff is None:
            return
        last_state = await self.async_get_last_state()
        last_data = await self.async_get_last_sensor_data()
        if (
            last_state is None
            or last_data is None
            or not isinstance(last_data.native_value, (int, float))
        ):
            return
        cycle_start = last_state.attributes.get("cycle_start")
        last_reset = (
            dt_util.parse_datetime(cycle_start)
            if isinstance(cycle_start, str)
            else None
        )
        self._tracker.restore_total(
            self._tariff, float(last_data.native_value), last_reset
        )

    @property
    def native_value(self) -> float:
        """Return value."""
        if self._tariff is None:
            total = sum(self._tracker.get_total(t) for t in self._tracker.tariffs)
        else:
            total = self._tracker.get_total(self._tariff)
        return round(total, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        return {"cycle_start": self._tracker.last_reset.isoformat()}

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        self._tracker.update(data, self.coordinator.last_update_success_time)
        super()._handle_coordinator_update()


class QubeSCOPSensor(QubeEntity, SensorEntity):
    """Seasonal COP over the current day/month cycle."""

    _attr_suggested_display_precision = 1
    _attr_native_unit_of_measurement = "CoP"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: QubeCoordinator,
        hub: QubeHub,
        electric_tracker: TariffEnergyTracker,
        thermic_tracker: TariffEnergyTracker,
        scope: str,
        translation_key: str,
        unique_base: str,
        version: str,
    ) -> None:
        """Initialize SCOP sensor; ``scope`` is a tariff or "total"."""
        super().__init__(coordinator, hub, version)
        self._electric = electric_tracker
        self._thermic = thermic_tracker
        self._scope = scope
        self._attr_translation_key = translation_key
        self.entity_id = f"sensor.{self._label}_{translation_key}"
        self._attr_unique_id = self._scoped_uid(unique_base)

    def _current_totals(self) -> tuple[float, float]:
        if self._scope == "total":
            elec = sum(self._electric.get_total(t) for t in self._electric.tariffs)
            therm = sum(self._thermic.get_total(t) for t in self._thermic.tariffs)
            return elec, therm
        return self._electric.get_total(self._scope), self._thermic.get_total(
            self._scope
        )

    @property
    def native_value(self) -> float | None:
        """Return the cycle SCOP, or None while it cannot be computed sensibly."""
        elec, therm = self._current_totals()
        if elec < SCOP_MIN_ELECTRIC_KWH:
            return None
        scop = therm / elec
        if scop < 0 or scop > SCOP_MAX_EXPECTED:
            return None
        return round(scop, 1)

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        token = self.coordinator.last_update_success_time
        self._electric.update(data, token)
        self._thermic.update(data, token)
        super()._handle_coordinator_update()
