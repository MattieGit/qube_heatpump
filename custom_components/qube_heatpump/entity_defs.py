"""Entity definitions for Qube Heat Pump, derived from the library's entity model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from python_qube_heatpump.entities.base import InputType, Platform

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

if TYPE_CHECKING:
    from python_qube_heatpump import EntityDef as LibraryEntityDef


@dataclass
class EntityDef:
    """Definition of a Qube entity for Home Assistant.

    This wraps the library's EntityDef with HA-specific metadata. The library
    already applies scale/offset/precision to the values it returns, so only
    presentation metadata lives here.

    ``unique_id``, ``vendor_id`` and ``translation_key`` are always the
    library entity key. They are kept as separate fields because the entity
    platforms read them under those names; treat them as one value.
    """

    platform: str
    name: str | None
    address: int
    vendor_id: str | None = None
    input_type: str | None = None
    write_type: str | None = None
    data_type: str | None = None
    unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | str | None = None
    state_class: SensorStateClass | str | None = None
    precision: int | None = None
    unique_id: str | None = None
    translation_key: str | None = None
    writable: bool = False


_PLATFORM_MAP = {
    Platform.SENSOR: "sensor",
    Platform.BINARY_SENSOR: "binary_sensor",
    Platform.SWITCH: "switch",
}

_INPUT_TYPE_MAP = {
    InputType.COIL: "coil",
    InputType.DISCRETE_INPUT: "discrete_input",
    InputType.INPUT_REGISTER: "input",
    InputType.HOLDING_REGISTER: "holding",
}

# Units used by the library's sensor definitions, mapped to device classes.
# ``%`` (pump/valve/compressor control levels) and ``rpm`` intentionally have
# no device class.
_UNIT_DEVICE_CLASS = {
    "°c": SensorDeviceClass.TEMPERATURE,
    "c": SensorDeviceClass.TEMPERATURE,
    "w": SensorDeviceClass.POWER,
    "kwh": SensorDeviceClass.ENERGY,
    "l/min": SensorDeviceClass.VOLUME_FLOW_RATE,
    "h": SensorDeviceClass.DURATION,
    "hours": SensorDeviceClass.DURATION,
}

_UNIT_PRECISION = {
    "°c": 1,
    "c": 1,
    "kwh": 2,
    "w": 0,
    "%": 1,
}


def _derive_device_class(unit: str | None, key: str) -> SensorDeviceClass | None:
    """Derive the Home Assistant device_class from the unit of measurement.

    The numeric ``status_code`` register deliberately gets no device class:
    the computed status sensor in sensor.py is the enum entity.
    """
    if not unit:
        return None
    return _UNIT_DEVICE_CLASS.get(unit.lower())


def _derive_state_class(
    unit: str | None, device_class: SensorDeviceClass | None, key: str
) -> SensorStateClass | None:
    """Derive the Home Assistant state_class from unit, device_class and key."""
    # Energy totals and working-hour counters only ever increase
    if device_class is SensorDeviceClass.ENERGY or "workinghours" in key.lower():
        return SensorStateClass.TOTAL_INCREASING
    if unit:
        return SensorStateClass.MEASUREMENT
    return None


def _derive_precision(
    unit: str | None, data_type: str | None, key: str | None = None
) -> int | None:
    """Derive suggested display precision from unit and data type."""
    # COP sensors: reduce precision to minimize state updates
    if key == "cop_calc":
        return 1
    if not unit:
        return None
    if (precision := _UNIT_PRECISION.get(unit.lower())) is not None:
        return precision
    # Float32 types often need decimal precision
    if data_type == "float32":
        return 2
    return None


def _library_to_ha_entity(lib_ent: LibraryEntityDef) -> EntityDef:
    """Convert a library EntityDef to an HA EntityDef."""
    input_type = _INPUT_TYPE_MAP.get(lib_ent.input_type) if lib_ent.input_type else None
    write_type = None
    if lib_ent.platform == Platform.SWITCH:
        write_type = input_type or "coil"

    data_type_str = lib_ent.data_type.value if lib_ent.data_type else None
    device_class = _derive_device_class(lib_ent.unit, lib_ent.key)
    state_class = _derive_state_class(lib_ent.unit, device_class, lib_ent.key)
    # Library precision wins when set (including 0); otherwise derive it
    precision = lib_ent.precision
    if precision is None:
        precision = _derive_precision(lib_ent.unit, data_type_str, lib_ent.key)

    return EntityDef(
        platform=_PLATFORM_MAP.get(lib_ent.platform, "sensor"),
        name=lib_ent.name,
        address=lib_ent.address,
        vendor_id=lib_ent.key,
        input_type=input_type,
        write_type=write_type,
        data_type=data_type_str,
        unit_of_measurement=lib_ent.unit,
        device_class=device_class,
        state_class=state_class,
        precision=precision,
        unique_id=lib_ent.key,
        translation_key=lib_ent.key,
        writable=lib_ent.writable,
    )
