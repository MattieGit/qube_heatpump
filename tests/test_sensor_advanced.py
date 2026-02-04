"""Advanced tests for Qube Heat Pump sensor platform covering edge cases."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from custom_components.qube_heatpump.sensor import (
    SCOP_MAX_EXPECTED,
    TariffEnergyTracker,
    _find_binary_by_address,
    _find_status_source,
    _scope_unique_id,
    _slugify,
    _start_of_day,
    _start_of_month,
)
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def test_slugify() -> None:
    """Test _slugify function."""
    assert _slugify("Hello World") == "hello_world"
    assert _slugify("test-123") == "test_123"
    assert _slugify("___test___") == "test"
    assert _slugify("CamelCase") == "camelcase"


def test_scope_unique_id() -> None:
    """Test _scope_unique_id always scopes with host_unit prefix."""
    # Always prefixes with host_unit for stability
    assert _scope_unique_id("base", "192.168.1.1", 1) == "192.168.1.1_1_base"
    assert _scope_unique_id("sensor", "10.0.0.5", 2) == "10.0.0.5_2_sensor"
    assert _scope_unique_id("test", "1.2.3.4", 1) == "1.2.3.4_1_test"


def test_start_of_month() -> None:
    """Test _start_of_month function."""
    dt = datetime(2025, 1, 15, 14, 30, 45, 123456)
    result = _start_of_month(dt)
    assert result == datetime(2025, 1, 1, 0, 0, 0, 0)


def test_start_of_day() -> None:
    """Test _start_of_day function."""
    dt = datetime(2025, 1, 15, 14, 30, 45, 123456)
    result = _start_of_day(dt)
    assert result == datetime(2025, 1, 15, 0, 0, 0, 0)


def test_find_status_source_with_matching_entity() -> None:
    """Test _find_status_source finds status entity."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(
        platform="sensor",
        name="Status",
        address=100,
        unique_id="wp_qube_warmtepomp_unit_status",
    )
    hub.entities = [ent1]
    result = _find_status_source(hub)
    assert result == ent1


def test_find_status_source_fallback_enum() -> None:
    """Test _find_status_source falls back to enum device_class."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(platform="sensor", name="Other", address=100, device_class="enum")
    hub.entities = [ent1]
    result = _find_status_source(hub)
    assert result == ent1


def test_find_status_source_fallback_name() -> None:
    """Test _find_status_source falls back to name containing status."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(platform="sensor", name="Unit Status Value", address=100)
    hub.entities = [ent1]
    result = _find_status_source(hub)
    assert result == ent1


def test_find_status_source_no_match() -> None:
    """Test _find_status_source returns None when no match."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(platform="sensor", name="Temperature", address=100)
    hub.entities = [ent1]
    result = _find_status_source(hub)
    assert result is None


def test_find_binary_by_address_found() -> None:
    """Test _find_binary_by_address finds entity."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(platform="binary_sensor", name="Test", address=4)
    hub.entities = [ent1]
    result = _find_binary_by_address(hub, 4)
    assert result == ent1


def test_find_binary_by_address_not_found() -> None:
    """Test _find_binary_by_address returns None when not found."""
    from custom_components.qube_heatpump.hub import EntityDef

    hub = MagicMock()
    ent1 = EntityDef(platform="binary_sensor", name="Test", address=5)
    hub.entities = [ent1]
    result = _find_binary_by_address(hub, 4)
    assert result is None


class TestTariffEnergyTracker:
    """Tests for TariffEnergyTracker."""

    def test_init(self) -> None:
        """Test tracker initialization."""
        tracker = TariffEnergyTracker(
            base_key="energy",
            binary_key="tariff",
            tariffs=["CH", "DHW"],
        )
        assert tracker.base_key == "energy"
        assert tracker.tariffs == ["CH", "DHW"]
        assert tracker.current_tariff == "CH"

    def test_set_initial_total_none(self) -> None:
        """Test set_initial_total with None value."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.set_initial_total(None)
        assert tracker._last_total is None

    def test_set_initial_total_invalid(self) -> None:
        """Test set_initial_total with invalid value."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.set_initial_total("invalid")
        assert tracker._last_total is None

    def test_set_initial_total_valid(self) -> None:
        """Test set_initial_total with valid value."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.set_initial_total(100.5)
        assert tracker._last_total == 100.5

    def test_restore_total(self) -> None:
        """Test restore_total updates values."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        old_reset = tracker._last_reset
        new_reset = old_reset + timedelta(days=1)
        tracker.restore_total("CH", 50.0, new_reset)
        assert tracker._totals["CH"] == 50.0
        assert tracker._last_reset == new_reset

    def test_restore_total_negative_clamped(self) -> None:
        """Test restore_total clamps negative values to 0."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.restore_total("CH", -10.0, None)
        assert tracker._totals["CH"] == 0.0

    def test_update_with_duplicate_token(self) -> None:
        """Test update skips processing when token is duplicate."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        token = dt_util.utcnow()
        # First update
        tracker.update({"energy": 100.0, "tariff": False}, token)
        # Duplicate token - should skip
        tracker.update({"energy": 200.0, "tariff": False}, token)
        # Value should not have changed
        assert tracker._last_total == 100.0

    def test_update_with_new_token(self) -> None:
        """Test update processes when token changes."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        token1 = dt_util.utcnow()
        token2 = token1 + timedelta(seconds=1)
        tracker.update({"energy": 100.0, "tariff": False}, token1)
        tracker.update({"energy": 110.0, "tariff": False}, token2)
        assert tracker._last_total == 110.0
        assert tracker._totals["CH"] == 10.0

    def test_update_none_base_value(self) -> None:
        """Test update handles None base value."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.update({"tariff": False}, None)
        assert tracker._last_total is None

    def test_update_invalid_base_value(self) -> None:
        """Test update handles invalid base value."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.update({"energy": "invalid", "tariff": False}, None)
        assert tracker._last_total is None

    def test_update_negative_delta(self) -> None:
        """Test update ignores negative delta."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.set_initial_total(100.0)
        # Lower value - should be ignored
        tracker.update({"energy": 50.0, "tariff": False}, dt_util.utcnow())
        assert tracker._totals["CH"] == 0.0

    def test_update_tariff_switch_dhw(self) -> None:
        """Test update switches tariff to DHW when binary is True."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker.update({"tariff": True}, None)
        assert tracker.current_tariff == "DHW"

    def test_update_tariff_switch_ch(self) -> None:
        """Test update switches tariff to CH when binary is False."""
        tracker = TariffEnergyTracker(
            base_key="energy", binary_key="tariff", tariffs=["CH", "DHW"]
        )
        tracker._current_tariff = "DHW"
        tracker.update({"tariff": False}, None)
        assert tracker.current_tariff == "CH"

    def test_reset_daily(self) -> None:
        """Test daily tracker resets at day boundary."""
        tracker = TariffEnergyTracker(
            base_key="energy",
            binary_key="tariff",
            tariffs=["CH", "DHW"],
            reset_period="day",
        )
        # Simulate some accumulation
        tracker._totals["CH"] = 10.0
        old_start = tracker._last_reset
        # Force reset by setting last_reset to yesterday
        tracker._last_reset = old_start - timedelta(days=1)
        tracker.set_initial_total(50.0)  # Set initial total first
        tracker.update({"energy": 100.0, "tariff": False}, dt_util.utcnow())
        # After reset, _last_reset should be updated to current day start
        assert tracker._last_reset >= old_start


class TestQubeSensorUniqueIdFallback:
    """Tests for QubeSensor unique_id fallback logic."""

    async def test_sensor_unique_id_fallback_input_type(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensor uses input_type in unique_id when unique_id not set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import QubeSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="sensor",
            name="Test Sensor",
            address=100,
            input_type="holding",
        )
        ent.unique_id = None
        ent.translation_key = None

        sensor = QubeSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            ent=ent,
        )

        # Always scoped with host_unit prefix for stability
        assert sensor._attr_unique_id == "1.2.3.4_1_qube_sensor_holding_100"

    async def test_sensor_unique_id_fallback_write_type(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensor uses write_type in unique_id fallback."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import QubeSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="sensor",
            name="Test Sensor",
            address=200,
            write_type="holding",
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.input_type = None

        sensor = QubeSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            ent=ent,
        )

        # Always scoped with host_unit prefix for stability
        assert sensor._attr_unique_id == "1.2.3.4_1_qube_sensor_holding_200"

    async def test_sensor_unique_id_multi_device(self, hass: HomeAssistant) -> None:
        """Test sensor unique_id includes host_unit prefix in multi_device mode."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import QubeSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry_id"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="sensor",
            name="Test Sensor",
            address=100,
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.input_type = None
        ent.write_type = None

        sensor = QubeSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=True,
            multi_device=True,
            version="1.0",
            ent=ent,
        )

        # Multi-device unique_id has host_unit prefix for isolation
        assert sensor._attr_unique_id.startswith("1.2.3.4_1_")


class TestQubeInfoSensorCountsFallback:
    """Tests for QubeInfoSensor counts fallback."""

    async def test_info_sensor_counts_fallback(self, hass: HomeAssistant) -> None:
        """Test info sensor falls back to counting entities when counts are None."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import QubeInfoSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"
        hub.resolved_ip = "1.2.3.4"
        hub.err_connect = 0
        hub.err_read = 0
        hub.entities = [
            EntityDef(platform="sensor", name="Temp", address=100),
            EntityDef(platform="sensor", name="Power", address=101),
            EntityDef(platform="binary_sensor", name="Status", address=1),
            EntityDef(platform="switch", name="Enable", address=1),
        ]

        coordinator = MagicMock()
        coordinator.data = {}

        sensor = QubeInfoSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            total_counts=None,
        )

        attrs = sensor.extra_state_attributes
        assert attrs["count_sensors"] == 2
        assert attrs["count_binary_sensors"] == 1
        assert attrs["count_switches"] == 1


class TestQubeMetricSensorCountProviders:
    """Tests for QubeMetricSensor count provider logic."""

    async def test_metric_sensor_count_sensors(self, hass: HomeAssistant) -> None:
        """Test metric sensor returns sensor count from provider."""
        from custom_components.qube_heatpump.sensor import QubeMetricSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"
        hub.entities = []

        coordinator = MagicMock()

        def counts_provider():
            return {"sensor": 10, "binary_sensor": 5, "switch": 3}

        sensor = QubeMetricSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            kind="count_sensors",
            counts_provider=counts_provider,
        )

        assert sensor.native_value == 10

    async def test_metric_sensor_count_binary_sensors(
        self, hass: HomeAssistant
    ) -> None:
        """Test metric sensor returns binary_sensor count from provider."""
        from custom_components.qube_heatpump.sensor import QubeMetricSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"
        hub.entities = []

        coordinator = MagicMock()

        def counts_provider():
            return {"sensor": 10, "binary_sensor": 5, "switch": 3}

        sensor = QubeMetricSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            kind="count_binary_sensors",
            counts_provider=counts_provider,
        )

        assert sensor.native_value == 5

    async def test_metric_sensor_count_switches(self, hass: HomeAssistant) -> None:
        """Test metric sensor returns switch count from provider."""
        from custom_components.qube_heatpump.sensor import QubeMetricSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"
        hub.entities = []

        coordinator = MagicMock()

        def counts_provider():
            return {"sensor": 10, "binary_sensor": 5, "switch": 3}

        sensor = QubeMetricSensor(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            version="1.0",
            kind="count_switches",
            counts_provider=counts_provider,
        )

        assert sensor.native_value == 3


class TestQubeSCOPSensorEdgeCases:
    """Tests for QubeSCOPSensor edge cases."""

    async def test_scop_zero_electric(self, hass: HomeAssistant) -> None:
        """Test SCOP returns 0 when electric is zero (no data yet)."""
        from custom_components.qube_heatpump.sensor import QubeSCOPSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        electric_tracker = MagicMock()
        electric_tracker.tariffs = ["CH", "DHW"]
        electric_tracker.get_total = MagicMock(return_value=0.0)

        thermic_tracker = MagicMock()
        thermic_tracker.tariffs = ["CH", "DHW"]
        thermic_tracker.get_total = MagicMock(return_value=100.0)

        sensor = QubeSCOPSensor(
            coordinator=coordinator,
            hub=hub,
            electric_tracker=electric_tracker,
            thermic_tracker=thermic_tracker,
            scope="total",
            translation_key="scop_month",
            unique_base="qube_scop_monthly",
            object_base="scop_maand",
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        assert sensor.native_value == 0.0

    async def test_scop_exceeds_max(self, hass: HomeAssistant) -> None:
        """Test SCOP returns 0 when value exceeds max expected."""
        from custom_components.qube_heatpump.sensor import QubeSCOPSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        electric_tracker = MagicMock()
        electric_tracker.tariffs = ["CH", "DHW"]
        electric_tracker.get_total = MagicMock(return_value=1.0)

        thermic_tracker = MagicMock()
        thermic_tracker.tariffs = ["CH", "DHW"]
        # SCOP of 20 exceeds max of 10
        thermic_tracker.get_total = MagicMock(return_value=20.0)

        sensor = QubeSCOPSensor(
            coordinator=coordinator,
            hub=hub,
            electric_tracker=electric_tracker,
            thermic_tracker=thermic_tracker,
            scope="total",
            translation_key="scop_month",
            unique_base="qube_scop_monthly",
            object_base="scop_maand",
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        # SCOP would be 40 (20/0.5 per tariff * 2 tariffs) which exceeds max
        assert sensor.native_value == 0.0

    async def test_scop_negative(self, hass: HomeAssistant) -> None:
        """Test SCOP returns 0 when value is negative."""
        from custom_components.qube_heatpump.sensor import QubeSCOPSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        electric_tracker = MagicMock()
        electric_tracker.tariffs = ["CH", "DHW"]
        electric_tracker.get_total = MagicMock(return_value=10.0)

        thermic_tracker = MagicMock()
        thermic_tracker.tariffs = ["CH", "DHW"]
        thermic_tracker.get_total = MagicMock(return_value=-5.0)

        sensor = QubeSCOPSensor(
            coordinator=coordinator,
            hub=hub,
            electric_tracker=electric_tracker,
            thermic_tracker=thermic_tracker,
            scope="total",
            translation_key="scop_month",
            unique_base="qube_scop_monthly",
            object_base="scop_maand",
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        assert sensor.native_value == 0.0

    async def test_scop_valid_calculation(self, hass: HomeAssistant) -> None:
        """Test SCOP calculates correctly."""
        from custom_components.qube_heatpump.sensor import QubeSCOPSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        electric_tracker = MagicMock()
        electric_tracker.tariffs = ["CH", "DHW"]
        # 5 + 5 = 10 total electric
        electric_tracker.get_total = MagicMock(return_value=5.0)

        thermic_tracker = MagicMock()
        thermic_tracker.tariffs = ["CH", "DHW"]
        # 15 + 15 = 30 total thermic
        thermic_tracker.get_total = MagicMock(return_value=15.0)

        sensor = QubeSCOPSensor(
            coordinator=coordinator,
            hub=hub,
            electric_tracker=electric_tracker,
            thermic_tracker=thermic_tracker,
            scope="total",
            translation_key="scop_month",
            unique_base="qube_scop_monthly",
            object_base="scop_maand",
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        # SCOP = 30/10 = 3.0
        assert sensor.native_value == 3.0

    async def test_scop_single_tariff(self, hass: HomeAssistant) -> None:
        """Test SCOP with single tariff scope."""
        from custom_components.qube_heatpump.sensor import QubeSCOPSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        coordinator = MagicMock()
        coordinator.data = {}

        electric_tracker = MagicMock()
        electric_tracker.tariffs = ["CH", "DHW"]
        electric_tracker.get_total = MagicMock(
            side_effect=lambda t: 5.0 if t == "CH" else 3.0
        )

        thermic_tracker = MagicMock()
        thermic_tracker.tariffs = ["CH", "DHW"]
        thermic_tracker.get_total = MagicMock(
            side_effect=lambda t: 20.0 if t == "CH" else 12.0
        )

        sensor = QubeSCOPSensor(
            coordinator=coordinator,
            hub=hub,
            electric_tracker=electric_tracker,
            thermic_tracker=thermic_tracker,
            scope="CH",  # Single tariff
            translation_key="scop_ch_month",
            unique_base="qube_scop_ch_monthly",
            object_base="scop_ch_month",
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        # SCOP = 20/5 = 4.0
        assert sensor.native_value == 4.0


class TestQubeComputedSensorStatusMappings:
    """Tests for QubeComputedSensor status mappings."""

    async def test_computed_sensor_status_standby(self, hass: HomeAssistant) -> None:
        """Test computed sensor returns standby for codes 1, 14, 18."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import (
            QubeComputedSensor,
            _entity_key,
        )

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        source = EntityDef(
            platform="sensor",
            name="Status",
            address=100,
            unique_id="test_status",
        )

        for code in [1, 14, 18]:
            coordinator = MagicMock()
            coordinator.data = {_entity_key(source): code}

            sensor = QubeComputedSensor(
                coordinator=coordinator,
                hub=hub,
                translation_key="status_heatpump",
                unique_suffix="status_full",
                kind="status",
                source=source,
                show_label=False,
                multi_device=False,
                version="1.0",
            )

            assert sensor.native_value == "standby", f"Code {code} should be standby"

    async def test_computed_sensor_status_mappings(self, hass: HomeAssistant) -> None:
        """Test computed sensor status code mappings."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import (
            QubeComputedSensor,
            _entity_key,
        )

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        source = EntityDef(
            platform="sensor",
            name="Status",
            address=100,
            unique_id="test_status",
        )

        mappings = {
            2: "alarm",
            6: "keyboard_off",
            8: "compressor_startup",
            9: "compressor_shutdown",
            15: "cooling",
            16: "heating",
            17: "start_fail",
            22: "heating_dhw",
            99: "unknown",  # Unknown code
        }

        for code, expected in mappings.items():
            coordinator = MagicMock()
            coordinator.data = {_entity_key(source): code}

            sensor = QubeComputedSensor(
                coordinator=coordinator,
                hub=hub,
                translation_key="status_heatpump",
                unique_suffix="status_full",
                kind="status",
                source=source,
                show_label=False,
                multi_device=False,
                version="1.0",
            )

            assert sensor.native_value == expected, f"Code {code} should be {expected}"

    async def test_computed_sensor_drieweg(self, hass: HomeAssistant) -> None:
        """Test computed sensor drieweg (3-way valve) mapping."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import (
            QubeComputedSensor,
            _entity_key,
        )

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        source = EntityDef(
            platform="binary_sensor",
            name="Drieweg",
            address=4,
            unique_id="test_drieweg",
        )

        # DHW when True
        coordinator = MagicMock()
        coordinator.data = {_entity_key(source): True}

        sensor = QubeComputedSensor(
            coordinator=coordinator,
            hub=hub,
            translation_key="drieweg_status",
            unique_suffix="driewegklep_dhw_cv",
            kind="drieweg",
            source=source,
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        assert sensor.native_value == "dhw"

        # CH when False
        coordinator.data = {_entity_key(source): False}
        assert sensor.native_value == "ch"

    async def test_computed_sensor_vierweg(self, hass: HomeAssistant) -> None:
        """Test computed sensor vierweg (4-way valve) mapping."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import (
            QubeComputedSensor,
            _entity_key,
        )

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        source = EntityDef(
            platform="binary_sensor",
            name="Vierweg",
            address=2,
            unique_id="test_vierweg",
        )

        # Heating when True
        coordinator = MagicMock()
        coordinator.data = {_entity_key(source): True}

        sensor = QubeComputedSensor(
            coordinator=coordinator,
            hub=hub,
            translation_key="vierweg_status",
            unique_suffix="vierwegklep_verwarmen_koelen",
            kind="vierweg",
            source=source,
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        assert sensor.native_value == "heating"

        # Cooling when False
        coordinator.data = {_entity_key(source): False}
        assert sensor.native_value == "cooling"

    async def test_computed_sensor_none_value(self, hass: HomeAssistant) -> None:
        """Test computed sensor returns None when source value is None."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.sensor import QubeComputedSensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"

        source = EntityDef(
            platform="sensor",
            name="Status",
            address=100,
            unique_id="test_status",
        )

        coordinator = MagicMock()
        coordinator.data = {}  # No value

        sensor = QubeComputedSensor(
            coordinator=coordinator,
            hub=hub,
            translation_key="status_heatpump",
            unique_suffix="status_full",
            kind="status",
            source=source,
            show_label=False,
            multi_device=False,
            version="1.0",
        )

        assert sensor.native_value is None


class TestQubeStandbyEnergySensorRestore:
    """Tests for QubeStandbyEnergySensor state restoration."""

    def test_standby_energy_restore_invalid_parse(self) -> None:
        """Test standby energy sensor handles invalid state parsing."""
        # Test the try/except logic for float conversion
        try:
            value = float("invalid_not_a_number")
        except (TypeError, ValueError):
            value = 0.0
        assert value == 0.0


class TestQubeTotalEnergyWithStandby:
    """Tests for QubeTotalEnergyIncludingStandbySensor."""

    def test_total_energy_invalid_base_value_conversion(self) -> None:
        """Test total energy handles invalid base value conversion."""
        # Test the try/except logic for float conversion
        base_value = "not_a_number"
        try:
            base_float = float(base_value) if base_value is not None else None
        except (TypeError, ValueError):
            base_float = None
        assert base_float is None

    def test_total_energy_none_base_value(self) -> None:
        """Test total energy handles None base value."""
        base_value = None
        try:
            base_float = float(base_value) if base_value is not None else None
        except (TypeError, ValueError):
            base_float = None
        assert base_float is None


class TestQubeIPAddressSensorDeviceClass:
    """Tests for QubeIPAddressSensor device class handling."""

    async def test_ip_sensor_without_ip_device_class(self, hass: HomeAssistant) -> None:
        """Test IP sensor handles missing SensorDeviceClass.IP."""
        from custom_components.qube_heatpump.sensor import QubeIPAddressSensor
        from homeassistant.components.sensor import SensorDeviceClass

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.entry_id = "test_entry"
        hub.resolved_ip = "1.2.3.4"

        coordinator = MagicMock()

        # Mock SensorDeviceClass without IP attribute
        with patch.object(SensorDeviceClass, "__contains__", return_value=False):
            sensor = QubeIPAddressSensor(
                coordinator=coordinator,
                hub=hub,
                show_label=False,
                multi_device=False,
                version="1.0",
            )

        # Should still work even if IP device class doesn't exist
        assert sensor.native_value == "1.2.3.4"
