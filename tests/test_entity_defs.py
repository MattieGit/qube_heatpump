"""Tests for the library -> Home Assistant entity definition mapping."""

from __future__ import annotations

from python_qube_heatpump import SENSORS

from custom_components.qube_heatpump.entity_defs import (
    _derive_device_class,
    _derive_state_class,
    _library_to_ha_entity,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


def test_library_precision_zero_is_kept() -> None:
    """A library precision of 0 must not be replaced by the derived default."""
    ent = _library_to_ha_entity(SENSORS["compressor_speed"])
    assert SENSORS["compressor_speed"].precision == 0
    assert ent.precision == 0


def test_percent_unit_has_no_device_class() -> None:
    """Percent registers are control levels, not power factors."""
    assert _derive_device_class("%", "comppwrreq") is None
    ent = _library_to_ha_entity(SENSORS["comppwrreq"])
    assert ent.device_class is None
    assert ent.state_class == SensorStateClass.MEASUREMENT


def test_flow_unit_maps_to_volume_flow_rate() -> None:
    """L/min registers get the volume flow rate device class."""
    ent = _library_to_ha_entity(SENSORS["flow"])
    assert ent.device_class == SensorDeviceClass.VOLUME_FLOW_RATE
    assert ent.state_class == SensorStateClass.MEASUREMENT


def test_status_code_is_not_an_enum() -> None:
    """The numeric status register is a plain sensor; the computed sensor is the enum."""
    ent = _library_to_ha_entity(SENSORS["status_code"])
    assert ent.device_class is None
    assert ent.state_class is None


def test_derivation_returns_enum_members() -> None:
    """Derived classes are HA enum members (still equal to their string values)."""
    device_class = _derive_device_class("kWh", "energy_total_electric")
    assert device_class is SensorDeviceClass.ENERGY
    assert device_class == "energy"
    state_class = _derive_state_class("kWh", device_class, "energy_total_electric")
    assert state_class is SensorStateClass.TOTAL_INCREASING
    assert state_class == "total_increasing"
    assert _derive_state_class("h", None, "workinghours_heat_hrsret") is (
        SensorStateClass.TOTAL_INCREASING
    )
    assert _derive_device_class("h", "workinghours_heat_hrsret") is (
        SensorDeviceClass.DURATION
    )


def test_every_library_sensor_maps_without_string_classes() -> None:
    """No library sensor ends up with a plain-string device or state class."""
    for lib_ent in SENSORS.values():
        ent = _library_to_ha_entity(lib_ent)
        assert ent.unique_id == ent.vendor_id == ent.translation_key == lib_ent.key
        if ent.device_class is not None:
            assert isinstance(ent.device_class, SensorDeviceClass)
        if ent.state_class is not None:
            assert isinstance(ent.state_class, SensorStateClass)
