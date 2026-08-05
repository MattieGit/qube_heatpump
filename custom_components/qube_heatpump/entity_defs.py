"""Entity definitions for Qube Heat Pump, derived from the library's entity model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from python_qube_heatpump.entities.base import InputType, Platform

if TYPE_CHECKING:
    from python_qube_heatpump import EntityDef as LibraryEntityDef


@dataclass
class EntityDef:
    """Definition of a Qube entity for Home Assistant.

    This wraps the library's EntityDef with HA-specific metadata.
    """

    platform: str
    name: str | None
    address: int
    vendor_id: str | None = None
    input_type: str | None = None
    write_type: str | None = None
    data_type: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    precision: int | None = None
    unique_id: str | None = None
    offset: float | None = None
    scale: float | None = None
    translation_key: str | None = None
    writable: bool = False
    # Reference to the library's entity definition
    _library_entity: LibraryEntityDef | None = None


def _derive_device_class(unit: str | None, key: str) -> str | None:
    """Derive Home Assistant device_class from unit of measurement."""
    if not unit:
        # Check key for status/enum entities
        if "status" in key.lower() or key == "unitstatus":
            return "enum"
        return None

    unit_lower = unit.lower()
    if unit_lower in ("°c", "c"):
        return "temperature"
    if unit_lower == "w":
        return "power"
    if unit_lower == "kwh":
        return "energy"
    if unit_lower == "%":
        return "power_factor"
    if unit_lower == "hz":
        return "frequency"
    if unit_lower == "bar":
        return "pressure"
    if unit_lower in ("h", "hours"):
        return "duration"
    return None


def _derive_state_class(
    unit: str | None, device_class: str | None, key: str
) -> str | None:
    """Derive Home Assistant state_class from unit and device_class."""
    if device_class == "enum":
        return None

    # Energy sensors are typically total_increasing
    if device_class == "energy" or (unit and unit.lower() == "kwh"):
        return "total_increasing"

    # Working hours and accumulated values are total_increasing
    key_lower = key.lower()
    if "workinghours" in key_lower or "acumulated" in key_lower:
        return "total_increasing"

    # Most other numeric sensors are measurements
    if unit:
        return "measurement"

    return None


def _derive_precision(
    unit: str | None, data_type: str | None, key: str | None = None
) -> int | None:
    """Derive suggested display precision from unit and data type."""
    # Special handling for COP sensors - reduce precision to minimize updates
    if key and key in ("cop_calc", "generalmng_cop"):
        return 1

    if not unit:
        return None

    unit_lower = unit.lower()
    if unit_lower in ("°c", "c"):
        return 1
    if unit_lower == "kwh":
        return 2
    if unit_lower == "w":
        return 0
    if unit_lower == "%":
        return 1
    if unit_lower == "bar":
        return 2

    # Float32 types often need decimal precision
    if data_type == "float32":
        return 2

    return None


def _library_to_ha_entity(lib_ent: LibraryEntityDef) -> EntityDef:
    """Convert a library EntityDef to an HA EntityDef."""
    # Map platform enum to string
    platform_map = {
        Platform.SENSOR: "sensor",
        Platform.BINARY_SENSOR: "binary_sensor",
        Platform.SWITCH: "switch",
    }

    # Map input type enum to string
    input_type_map = {
        InputType.COIL: "coil",
        InputType.DISCRETE_INPUT: "discrete_input",
        InputType.INPUT_REGISTER: "input",
        InputType.HOLDING_REGISTER: "holding",
    }

    # Determine write_type for switches
    write_type = None
    if lib_ent.platform == Platform.SWITCH:
        write_type = input_type_map.get(lib_ent.input_type, "coil")

    # Derive HA-specific metadata
    data_type_str = lib_ent.data_type.value if lib_ent.data_type else None
    device_class = _derive_device_class(lib_ent.unit, lib_ent.key)
    state_class = _derive_state_class(lib_ent.unit, device_class, lib_ent.key)
    # Use library precision if set, otherwise derive from unit/data_type/key
    precision = getattr(lib_ent, "precision", None) or _derive_precision(
        lib_ent.unit, data_type_str, lib_ent.key
    )

    return EntityDef(
        platform=platform_map.get(lib_ent.platform, "sensor"),
        name=lib_ent.name,
        address=lib_ent.address,
        vendor_id=lib_ent.key,
        input_type=input_type_map.get(lib_ent.input_type)
        if lib_ent.input_type
        else None,
        write_type=write_type,
        data_type=data_type_str,
        unit_of_measurement=lib_ent.unit,
        device_class=device_class,
        state_class=state_class,
        precision=precision,
        offset=lib_ent.offset,
        scale=lib_ent.scale,
        unique_id=lib_ent.key,
        translation_key=lib_ent.key,
        writable=lib_ent.writable,
        _library_entity=lib_ent,
    )
