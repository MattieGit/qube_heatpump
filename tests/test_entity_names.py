from __future__ import annotations

from types import SimpleNamespace
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
from custom_components.qube_heatpump.sensor import (
    QubeInfoSensor,
    QubeIPAddressSensor,
    QubeMetricSensor,
    WPQubeComputedSensor,
    WPQubeSensor,
)
from custom_components.qube_heatpump.button import QubeReloadButton
from custom_components.qube_heatpump.binary_sensor import WPQubeBinarySensor
from custom_components.qube_heatpump.switch import WPQubeSwitch


class _DummyCoordinator:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

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
