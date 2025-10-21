from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
import math
import sys


class _DummyModbusException(Exception):
    """Fallback Modbus exception used for import stubbing."""


class _DummyAsyncModbusTcpClient:
    def __init__(self, *args, **kwargs):  # pragma: no cover - stub
        self.connected = True

    async def connect(self):  # pragma: no cover - stub
        return True

    def close(self):  # pragma: no cover - stub
        return None


_client_stub = SimpleNamespace(
    AsyncModbusTcpClient=_DummyAsyncModbusTcpClient,
    AsyncModbusSerialClient=_DummyAsyncModbusTcpClient,
    AsyncModbusUdpClient=_DummyAsyncModbusTcpClient,
)
_exceptions_stub = SimpleNamespace(ModbusException=_DummyModbusException)

sys.modules.setdefault("pymodbus", SimpleNamespace(client=_client_stub, exceptions=_exceptions_stub))
sys.modules.setdefault("pymodbus.client", _client_stub)
sys.modules.setdefault("pymodbus.exceptions", _exceptions_stub)

import pytest
from homeassistant.util import dt as dt_util

from custom_components.qube_heatpump.const import TARIFF_OPTIONS
from custom_components.qube_heatpump.sensor import (
    QubeInfoSensor,
    QubeIPAddressSensor,
    QubeMetricSensor,
    QubeStandbyEnergySensor,
    QubeStandbyPowerSensor,
    QubeTariffEnergySensor,
    QubeTotalEnergyIncludingStandbySensor,
    STANDBY_POWER_WATTS,
    TariffEnergyTracker,
    WPQubeComputedSensor,
    WPQubeSensor,
)
from custom_components.qube_heatpump.button import QubeReloadButton
from custom_components.qube_heatpump.binary_sensor import WPQubeBinarySensor
from custom_components.qube_heatpump.switch import WPQubeSwitch


class _DummyCoordinator:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.last_update_success = True
        self.last_update_success_time = dt_util.utcnow()

    def async_add_listener(self, *_args, **_kwargs):  # pragma: no cover - stubbed
        return lambda: None


class _DummyHub:
    def __init__(self, label: str = "qube1") -> None:
        self.label = label
        self.host = "192.0.2.10"
        self.unit = 1
        self.entities: list[SimpleNamespace] = []
        self.err_connect = 0
        self.err_read = 0
        self.resolved_ip = "192.0.2.10"


def _base_entity(
    name: str = "Test Sensor",
    vendor_id: str = "test_sensor",
    platform: str = "sensor",
) -> SimpleNamespace:
    return SimpleNamespace(
        platform=platform,
        name=name,
        address=1,
        vendor_id=vendor_id,
        unique_id=f"{vendor_id}_unique",
        input_type="input",
        write_type=None,
        device_class=None,
        unit_of_measurement=None,
        state_class=None,
        precision=None,
    )


@pytest.mark.parametrize("show_label", [False, True])
def test_wpqube_sensor_friendly_name(show_label: bool) -> None:
    ent = _base_entity()
    sensor = WPQubeSensor(
        _DummyCoordinator(),
        host="192.0.2.10",
        unit=1,
        label="qube1",
        show_label=show_label,
        multi_device=True,
        version="1.0",
        ent=ent,
    )

    assert sensor.name == ent.name
    expected_object = f"{ent.vendor_id}_qube1" if show_label else ent.vendor_id
    assert getattr(sensor, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_wpqube_binary_sensor_friendly_name(show_label: bool) -> None:
    ent = _base_entity(name="Binary Test", vendor_id="binary_test", platform="binary_sensor")
    binary = WPQubeBinarySensor(
        _DummyCoordinator(),
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        ent=ent,
    )

    assert binary.name == ent.name
    expected_object = f"{ent.vendor_id}_qube1" if show_label else ent.vendor_id
    assert getattr(binary, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_wpqube_switch_friendly_name(show_label: bool) -> None:
    ent = _base_entity(name="Switch Test", vendor_id="switch_test", platform="switch")
    switch = WPQubeSwitch(
        _DummyCoordinator(),
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        ent=ent,
    )

    assert switch.name == ent.name
    expected_object = f"{ent.vendor_id}_qube1" if show_label else ent.vendor_id
    assert getattr(switch, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_info_sensor_name_no_label(show_label: bool) -> None:
    hub = _DummyHub()
    sensor = QubeInfoSensor(
        _DummyCoordinator(),
        hub,
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert sensor.name == "Qube info"
    expected_object = f"qube_info_{hub.label}" if show_label else "qube_info"
    assert getattr(sensor, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_metric_sensor_name_no_label(show_label: bool) -> None:
    hub = _DummyHub()
    metric = QubeMetricSensor(
        _DummyCoordinator(),
        hub,
        show_label=show_label,
        multi_device=True,
        version="1.0",
        kind="errors_connect",
    )

    assert metric.name == "Qube connect errors"
    expected_object = (
        f"qube_metric_errors_connect_{hub.label}" if show_label else "qube_metric_errors_connect"
    )
    assert getattr(metric, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_ip_sensor_name_no_label(show_label: bool) -> None:
    hub = _DummyHub()
    ip_sensor = QubeIPAddressSensor(
        _DummyCoordinator(),
        hub,
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert ip_sensor.name == "Qube IP address"
    expected_object = f"qube_ip_address_{hub.label}" if show_label else "qube_ip_address"
    assert getattr(ip_sensor, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_reload_button_name_no_label(show_label: bool) -> None:
    button = QubeReloadButton(
        _DummyCoordinator(),
        _DummyHub(),
        entry_id="entry1",
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert button.name == "Reload"
    expected_object = f"qube_reload_qube1" if show_label else "qube_reload"
    assert getattr(button, "_attr_suggested_object_id", None) == expected_object


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_standby_power_object_id(show_label: bool) -> None:
    sensor = QubeStandbyPowerSensor(
        _DummyCoordinator(),
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert sensor.name == "Standby vermogen"
    expected = "qube_standby_power_qube1" if show_label else "qube_standby_power"
    assert getattr(sensor, "_attr_suggested_object_id", None) == expected


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_standby_energy_object_id(show_label: bool) -> None:
    sensor = QubeStandbyEnergySensor(
        _DummyCoordinator(),
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert sensor.name == "Standby verbruik"
    expected = "qube_standby_energy_qube1" if show_label else "qube_standby_energy"
    assert getattr(sensor, "_attr_suggested_object_id", None) == expected


@pytest.mark.parametrize("show_label", [False, True])
def test_qube_total_energy_object_id(show_label: bool) -> None:
    coordinator = _DummyCoordinator()
    standby = QubeStandbyEnergySensor(
        coordinator,
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    combined = QubeTotalEnergyIncludingStandbySensor(
        coordinator,
        _DummyHub(),
        show_label=show_label,
        multi_device=True,
        version="1.0",
        base_unique_id="generalmng_acumulatedpwr_qube1",
        standby_sensor=standby,
    )

    assert combined.name == "Totaal elektrisch verbruik (incl. standby)"
    expected = "qube_total_energy_with_standby_qube1" if show_label else "qube_total_energy_with_standby"
    assert getattr(combined, "_attr_suggested_object_id", None) == expected


@pytest.mark.asyncio
async def test_standby_energy_integration(monkeypatch: pytest.MonkeyPatch, hass) -> None:
    coordinator = _DummyCoordinator()
    hub = _DummyHub()

    now = datetime(2025, 1, 1, tzinfo=dt_util.UTC)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: now)

    sensor = QubeStandbyEnergySensor(coordinator, hub, show_label=False, multi_device=False, version="1.0")
    sensor.hass = hass
    sensor.entity_id = "sensor.qube_standby_energy"
    await sensor.async_added_to_hass()

    later = now + timedelta(hours=1)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: later)
    coordinator.last_update_success_time = later

    sensor._handle_coordinator_update()

    assert math.isclose(sensor.native_value, 0.017, rel_tol=1e-3)


@pytest.mark.asyncio
async def test_total_energy_combines_base(monkeypatch: pytest.MonkeyPatch, hass) -> None:
    coordinator = _DummyCoordinator()
    hub = _DummyHub()

    base_key = "generalmng_acumulatedpwr"

    now = datetime(2025, 1, 1, tzinfo=dt_util.UTC)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: now)

    standby = QubeStandbyEnergySensor(coordinator, hub, show_label=False, multi_device=False, version="1.0")
    standby.hass = hass
    standby.entity_id = "sensor.qube_standby_energy"
    await standby.async_added_to_hass()

    total = QubeTotalEnergyIncludingStandbySensor(
        coordinator,
        hub,
        show_label=False,
        multi_device=False,
        version="1.0",
        base_unique_id=base_key,
        standby_sensor=standby,
    )
    total.hass = hass
    total.entity_id = "sensor.qube_total_energy_with_standby"
    await total.async_added_to_hass()

    later = now + timedelta(hours=2)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: later)
    coordinator.last_update_success_time = later

    coordinator.data[base_key] = 12.5

    standby._handle_coordinator_update()
    total._handle_coordinator_update()

    expected = 12.5 + (STANDBY_POWER_WATTS / 1000.0) * 2
    assert math.isclose(total.native_value or 0.0, expected, rel_tol=1e-3)


@pytest.mark.asyncio
async def test_tariff_energy_split(monkeypatch: pytest.MonkeyPatch, hass) -> None:
    coordinator = _DummyCoordinator()
    hub = _DummyHub()

    base_key = "generalmng_acumulatedpwr"
    binary_key = "dout_threewayvlv_val"

    tracker = TariffEnergyTracker(base_key, binary_key, list(TARIFF_OPTIONS))
    tracker.set_initial_total(100.0)

    cv_sensor = QubeTariffEnergySensor(
        coordinator,
        hub,
        tracker,
        tariff="CV",
        name_suffix="Elektrisch verbruik CV (maand)",
        show_label=False,
        multi_device=False,
        version="1.0",
    )
    cv_sensor.hass = hass
    cv_sensor.entity_id = "sensor.qube_energy_tariff_cv"
    await cv_sensor.async_added_to_hass()

    sww_sensor = QubeTariffEnergySensor(
        coordinator,
        hub,
        tracker,
        tariff="SWW",
        name_suffix="Elektrisch verbruik SWW (maand)",
        show_label=False,
        multi_device=False,
        version="1.0",
    )
    sww_sensor.hass = hass
    sww_sensor.entity_id = "sensor.qube_energy_tariff_sww"
    await sww_sensor.async_added_to_hass()

    now = datetime(2025, 1, 1, tzinfo=dt_util.UTC)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: now)
    coordinator.data[base_key] = 100.0
    coordinator.data[binary_key] = False
    coordinator.last_update_success_time = now

    cv_sensor._handle_coordinator_update()
    sww_sensor._handle_coordinator_update()

    assert cv_sensor.name == "Elektrisch verbruik CV (maand)"
    assert sww_sensor.name == "Elektrisch verbruik SWW (maand)"

    later = now + timedelta(minutes=30)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: later)
    coordinator.last_update_success_time = later
    coordinator.data[base_key] = 102.0
    coordinator.data[binary_key] = False

    cv_sensor._handle_coordinator_update()
    sww_sensor._handle_coordinator_update()

    assert math.isclose(cv_sensor.native_value, 2.0, rel_tol=1e-3)
    assert math.isclose(sww_sensor.native_value, 0.0, rel_tol=1e-3)

    later2 = later + timedelta(minutes=30)
    monkeypatch.setattr("custom_components.qube_heatpump.sensor.dt_util.utcnow", lambda: later2)
    coordinator.last_update_success_time = later2
    coordinator.data[base_key] = 103.5
    coordinator.data[binary_key] = True

    cv_sensor._handle_coordinator_update()
    sww_sensor._handle_coordinator_update()

    assert math.isclose(cv_sensor.native_value, 2.0, rel_tol=1e-3)
    assert math.isclose(sww_sensor.native_value, 1.5, rel_tol=1e-3)


@pytest.mark.parametrize("show_label", [False, True])
def test_wpqube_computed_sensor_name_no_label(show_label: bool) -> None:
    hub = _DummyHub()
    source = _base_entity(name="Source Sensor", vendor_id="source_sensor")
    computed = WPQubeComputedSensor(
        _DummyCoordinator(),
        hub,
        name="Computed",
        unique_suffix="computed",
        kind="status",
        source=source,
        show_label=show_label,
        multi_device=True,
        version="1.0",
    )

    assert computed.name == "Computed"
    expected_object = f"computed_{hub.label}" if show_label else computed._object_base
    assert getattr(computed, "_attr_suggested_object_id", None) == expected_object
