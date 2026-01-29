# HACS Integration Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update HACS integration to use official HA architecture patterns and the `python-qube-heatpump` library with ~89 entities across sensor, binary_sensor, switch, button, and select platforms.

**Architecture:** Library provides EntityDef dataclasses and extended QubeClient API. Integration maps library entities to HA entity descriptions, uses DataUpdateCoordinator pattern, and follows official HA integration structure.

**Tech Stack:** Python 3.12+, pymodbus, pytest, ruff, mypy, pre-commit, Home Assistant 2024.1+

---

## Phase 1: Library Updates (`python-qube-heatpump`)

### Task 1: Create entities/base.py with enums and EntityDef

**Files:**
- Create: `~/Github/python-qube-heatpump/src/python_qube_heatpump/entities/base.py`
- Test: `~/Github/python-qube-heatpump/tests/test_entities.py`

**Step 1: Write the failing test**

```python
# tests/test_entities.py
"""Tests for entity definitions."""

import pytest
from python_qube_heatpump.entities.base import (
    DataType,
    EntityDef,
    InputType,
    Platform,
)


def test_input_type_enum():
    """Test InputType enum values."""
    assert InputType.COIL.value == "coil"
    assert InputType.DISCRETE_INPUT.value == "discrete_input"
    assert InputType.INPUT_REGISTER.value == "input"
    assert InputType.HOLDING_REGISTER.value == "holding"


def test_data_type_enum():
    """Test DataType enum values."""
    assert DataType.FLOAT32.value == "float32"
    assert DataType.INT16.value == "int16"
    assert DataType.UINT16.value == "uint16"


def test_platform_enum():
    """Test Platform enum values."""
    assert Platform.SENSOR.value == "sensor"
    assert Platform.BINARY_SENSOR.value == "binary_sensor"
    assert Platform.SWITCH.value == "switch"


def test_entity_def_creation():
    """Test EntityDef dataclass creation."""
    entity = EntityDef(
        key="temp_supply",
        name="Supply temperature",
        address=20,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    )
    assert entity.key == "temp_supply"
    assert entity.name == "Supply temperature"
    assert entity.address == 20
    assert entity.input_type == InputType.INPUT_REGISTER
    assert entity.data_type == DataType.FLOAT32
    assert entity.platform == Platform.SENSOR
    assert entity.unit == "°C"
    assert entity.scale is None
    assert entity.offset is None
    assert entity.writable is False


def test_entity_def_is_frozen():
    """Test EntityDef is immutable."""
    entity = EntityDef(
        key="test",
        name="Test",
        address=0,
        input_type=InputType.COIL,
        platform=Platform.BINARY_SENSOR,
    )
    with pytest.raises(AttributeError):
        entity.key = "changed"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'python_qube_heatpump.entities'"

**Step 3: Create the entities directory and base.py**

```bash
mkdir -p ~/Github/python-qube-heatpump/src/python_qube_heatpump/entities
```

```python
# src/python_qube_heatpump/entities/base.py
"""Base classes and enums for entity definitions."""

from dataclasses import dataclass
from enum import Enum


class InputType(str, Enum):
    """Modbus input type for reading values."""

    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"
    INPUT_REGISTER = "input"
    HOLDING_REGISTER = "holding"


class DataType(str, Enum):
    """Data type for register values."""

    FLOAT32 = "float32"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"


class Platform(str, Enum):
    """Home Assistant platform type."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    SWITCH = "switch"


@dataclass(frozen=True)
class EntityDef:
    """Definition of a Qube heat pump entity.

    This dataclass defines the protocol-level properties of an entity.
    Home Assistant-specific metadata (device_class, state_class, etc.)
    should be added by the integration, not here.
    """

    # Identity
    key: str
    """Unique identifier, e.g., 'temp_supply'."""

    name: str
    """Human-readable name, e.g., 'Supply temperature'."""

    # Modbus specifics
    address: int
    """Register or coil address."""

    input_type: InputType
    """How to read from device (coil, discrete_input, input, holding)."""

    data_type: DataType | None = None
    """Data type for registers. None for coils/discrete inputs."""

    # Platform hint
    platform: Platform = Platform.SENSOR
    """Which HA platform this entity belongs to."""

    # Value transformation
    scale: float | None = None
    """Multiply raw value by this factor."""

    offset: float | None = None
    """Add this to the scaled value."""

    # Unit (protocol-level)
    unit: str | None = None
    """Unit of measurement, e.g., '°C', 'kWh', 'W'."""

    # Write capability
    writable: bool = False
    """Whether this entity can be written to."""
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/entities/ tests/test_entities.py
git commit -m "feat: add EntityDef dataclass and enums for entity definitions"
```

---

### Task 2: Create entities/binary_sensors.py

**Files:**
- Create: `~/Github/python-qube-heatpump/src/python_qube_heatpump/entities/binary_sensors.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_entities.py`
- Reference: `~/Github/qube_heatpump/custom_components/qube_heatpump/modbus.yaml`

**Step 1: Write the failing test**

Add to `tests/test_entities.py`:

```python
def test_binary_sensor_definitions_exist():
    """Test binary sensor definitions are available."""
    from python_qube_heatpump.entities.binary_sensors import BINARY_SENSORS

    # Check we have binary sensors
    assert len(BINARY_SENSORS) > 0

    # Check a specific one
    assert "dout_srcpmp_val" in BINARY_SENSORS
    entity = BINARY_SENSORS["dout_srcpmp_val"]
    assert entity.platform == Platform.BINARY_SENSOR
    assert entity.input_type == InputType.DISCRETE_INPUT
    assert entity.address == 0


def test_all_binary_sensors_have_required_fields():
    """Test all binary sensors have required fields."""
    from python_qube_heatpump.entities.binary_sensors import BINARY_SENSORS

    for key, entity in BINARY_SENSORS.items():
        assert entity.key == key, f"Key mismatch for {key}"
        assert entity.name, f"Missing name for {key}"
        assert entity.platform == Platform.BINARY_SENSOR, f"Wrong platform for {key}"
        assert entity.input_type in (
            InputType.DISCRETE_INPUT,
            InputType.COIL,
            InputType.HOLDING_REGISTER,
            InputType.INPUT_REGISTER,
        ), f"Invalid input_type for {key}"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py::test_binary_sensor_definitions_exist -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create binary_sensors.py**

Extract from modbus.yaml and create:

```python
# src/python_qube_heatpump/entities/binary_sensors.py
"""Binary sensor entity definitions for Qube Heat Pump."""

from .base import EntityDef, InputType, Platform

# Binary sensor definitions extracted from modbus.yaml
# All binary sensors use Platform.BINARY_SENSOR
_BINARY_SENSOR_DEFS: tuple[EntityDef, ...] = (
    EntityDef(
        key="dout_srcpmp_val",
        name="Source pump power supply",
        address=0,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_usrpmp_val",
        name="User pump power supply",
        address=1,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_fourwayvlv_val",
        name="Four-way valve control",
        address=2,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_cooling_val",
        name="Cooling active output",
        address=3,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_threewayvlv_val",
        name="Three-way valve output (CV/DHW)",
        address=4,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_bufferpmp_val",
        name="Buffer pump output",
        address=5,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_heaterstep1_val",
        name="Heater 1 output",
        address=6,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_heaterstep2_val",
        name="Heater 2 output",
        address=7,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dout_heaterstep3_val",
        name="Heater 3 output",
        address=8,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="keybonoff",
        name="Heat pump keypad status",
        address=9,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="al_maxtime_antileg_active",
        name="Alarm: Max time anti-legionella exceeded",
        address=10,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="al_maxtime_dhw_active",
        name="Alarm: Max time DHW exceeded",
        address=11,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="al_dewpoint_active",
        name="Alarm: Dewpoint activated",
        address=12,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="al_underfloorsafety_active",
        name="Alarm: Supply too hot (CV)",
        address=13,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="alrm_flw",
        name="Alarm: Flow CV",
        address=15,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="usralrms",
        name="Alarm: Collective alarm CV",
        address=16,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="coolingalrms",
        name="Alarm: Collective alarm cooling",
        address=17,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="heatingalrms",
        name="Alarm: Collective alarm heating",
        address=18,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="alarmmng_al_workinghour",
        name="Alarm: Working hours",
        address=19,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="srsalrm",
        name="Alarm: Collective alarm source",
        address=20,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="glbal",
        name="Global Alarm",
        address=21,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="alarmmng_al_pwrplus",
        name="Alarm: Collective alarm compressor",
        address=22,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="roomprb_en",
        name="Room sensor activated",
        address=23,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="plantdemand",
        name="Plant sensor demand",
        address=25,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="en_dhwpid",
        name="DHW controller enabled",
        address=26,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="plantprb_en",
        name="Plant sensor activated",
        address=27,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="bufferprb_en",
        name="Buffer sensor activated",
        address=28,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="id_demand",
        name="Digital input demand",
        address=29,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="id_summerwinter",
        name="Digital input summer mode activated",
        address=30,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="dewpoint",
        name="Digital input dewpoint activated",
        address=31,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="boostersecurity",
        name="Digital input booster activated",
        address=32,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="srcflw",
        name="Digital input source flow activated",
        address=33,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="daynightmode",
        name="Day/night mode status",
        address=34,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="thermostatdemand",
        name="Internal thermostat demand",
        address=35,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="req_antileg_1",
        name="Anti-legionella enabled",
        address=36,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="bms_demand",
        name="Heat demand active",
        address=37,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
    EntityDef(
        key="surplus_pv",
        name="PV surplus active",
        address=38,
        input_type=InputType.DISCRETE_INPUT,
        platform=Platform.BINARY_SENSOR,
    ),
)

# Export as dict for easy lookup by key
BINARY_SENSORS: dict[str, EntityDef] = {e.key: e for e in _BINARY_SENSOR_DEFS}
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/entities/binary_sensors.py tests/test_entities.py
git commit -m "feat: add binary sensor entity definitions"
```

---

### Task 3: Create entities/sensors.py

**Files:**
- Create: `~/Github/python-qube-heatpump/src/python_qube_heatpump/entities/sensors.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_entities.py`
- Reference: `~/Github/qube_heatpump/custom_components/qube_heatpump/modbus.yaml`

**Step 1: Write the failing test**

Add to `tests/test_entities.py`:

```python
def test_sensor_definitions_exist():
    """Test sensor definitions are available."""
    from python_qube_heatpump.entities.sensors import SENSORS

    assert len(SENSORS) > 0

    # Check core sensors exist
    assert "temp_supply" in SENSORS
    assert "temp_return" in SENSORS
    assert "power_thermic" in SENSORS

    # Verify a sensor's properties
    temp = SENSORS["temp_supply"]
    assert temp.platform == Platform.SENSOR
    assert temp.input_type == InputType.INPUT_REGISTER
    assert temp.data_type == DataType.FLOAT32
    assert temp.unit == "°C"


def test_all_sensors_have_required_fields():
    """Test all sensors have required fields."""
    from python_qube_heatpump.entities.sensors import SENSORS

    for key, entity in SENSORS.items():
        assert entity.key == key, f"Key mismatch for {key}"
        assert entity.name, f"Missing name for {key}"
        assert entity.platform == Platform.SENSOR, f"Wrong platform for {key}"
        assert entity.data_type is not None, f"Missing data_type for {key}"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py::test_sensor_definitions_exist -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create sensors.py**

Extract all sensors from modbus.yaml. This is a larger file - create it with all sensor definitions from the YAML. Key sensors include:

```python
# src/python_qube_heatpump/entities/sensors.py
"""Sensor entity definitions for Qube Heat Pump."""

from .base import DataType, EntityDef, InputType, Platform

_SENSOR_DEFS: tuple[EntityDef, ...] = (
    # Setpoints (Holding registers, readable as sensors)
    EntityDef(
        key="thermostat_heatsetp_day",
        name="Room setpoint heating (day)",
        address=27,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="thermostat_heatsetp_night",
        name="Room setpoint heating (night)",
        address=29,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="thermostat_coolsetp_day",
        name="Room setpoint cooling (day)",
        address=31,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="thermostat_coolsetp_night",
        name="Room setpoint cooling (night)",
        address=33,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="tapw_timeprogram_dt_bms",
        name="dT flow temperature DHW",
        address=43,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="tapw_timeprogram_dhws",
        name="Minimum temperature DHW",
        address=44,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="tapw_timeprogram_dhws_prog",
        name="DHW temperature (active program)",
        address=46,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="regulation_buffersetp_min",
        name="Minimum setpoint buffer regulation",
        address=99,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="usr_pid_heatsetp",
        name="Heat setpoint (no curve)",
        address=101,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="usr_pid_coolsetp",
        name="Cooling setpoint (no curve)",
        address=103,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="regulation_buffersetp_max",
        name="Max buffer setpoint (cooling)",
        address=169,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="tapw_timeprogram_dhwsetp_nolinq",
        name="User-defined DHW setpoint",
        address=173,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    # Input registers (read-only sensors)
    EntityDef(
        key="aout_usrpmp_val",
        name="User (CV) pump control %",
        address=4,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="%",
        scale=-1.0,
        offset=100.0,
    ),
    EntityDef(
        key="aout_srcpmp_val",
        name="Source pump control %",
        address=6,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="%",
        scale=-1.0,
        offset=100.0,
    ),
    EntityDef(
        key="aout_srcvalve_val",
        name="Source valve control %",
        address=8,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="%",
    ),
    EntityDef(
        key="dhw_regreq",
        name="DHW regulation demand %",
        address=14,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="%",
    ),
    EntityDef(
        key="comppwrreq",
        name="Compressor demand %",
        address=16,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="%",
    ),
    EntityDef(
        key="flow",
        name="Measured Flow",
        address=18,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="L/min",
    ),
    # Core temperature sensors (mapped to QubeState typed fields)
    EntityDef(
        key="temp_supply",
        name="Supply temperature CV",
        address=20,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_return",
        name="Return temperature CV",
        address=22,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_source_in",
        name="Source temperature from roof",
        address=24,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_source_out",
        name="Source temperature to roof",
        address=26,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_room",
        name="Room temperature",
        address=28,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_dhw",
        name="DHW temperature",
        address=30,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="temp_outside",
        name="Outside temperature",
        address=32,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="cop_calc",
        name="COP (calculated)",
        address=34,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
    ),
    EntityDef(
        key="power_thermic",
        name="Current power",
        address=36,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="W",
    ),
    EntityDef(
        key="status_code",
        name="Status code",
        address=38,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.UINT16,
        platform=Platform.SENSOR,
    ),
    EntityDef(
        key="regsetp",
        name="Calculated heat pump setpoint",
        address=39,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="coolsetp_1",
        name="Cooling setpoint",
        address=41,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="heatsetp_1",
        name="Heating setpoint",
        address=43,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="compressor_speed",
        name="Current compressor speed",
        address=45,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="rpm",
        scale=60.0,
    ),
    EntityDef(
        key="dhw_setp",
        name="DHW calculated setpoint",
        address=47,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="workinghours_dhw_hrsret",
        name="Working hours DHW",
        address=50,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="workinghours_heat_hrsret",
        name="Working hours heating",
        address=52,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="workinghours_cool_hrsret",
        name="Working hours cooling",
        address=54,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="workinghours_heater1_hrs",
        name="Working hours heater 1",
        address=56,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="workinghours_heater2_hrs",
        name="Working hours heater 2",
        address=58,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="workinghours_heater3_hrs",
        name="Working hours heater 3",
        address=60,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.INT16,
        platform=Platform.SENSOR,
        unit="h",
    ),
    EntityDef(
        key="power_electric",
        name="Total electric power (calculated)",
        address=61,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="W",
    ),
    EntityDef(
        key="plantsetp",
        name="Plant regulation setpoint",
        address=65,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="energy_total_electric",
        name="Total electric consumption (excl. standby)",
        address=69,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="kWh",
    ),
    EntityDef(
        key="energy_total_thermic",
        name="Total thermic yield",
        address=71,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="kWh",
    ),
    EntityDef(
        key="modbus_roomtemp",
        name="Linq room temperature",
        address=75,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="flow_rate",
        name="Measured Flow",
        address=18,
        input_type=InputType.INPUT_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="L/min",
    ),
    # Setpoints that map to QubeState typed fields
    EntityDef(
        key="setpoint_room_heat_day",
        name="Room setpoint heating (day)",
        address=27,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="setpoint_room_heat_night",
        name="Room setpoint heating (night)",
        address=29,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="setpoint_room_cool_day",
        name="Room setpoint cooling (day)",
        address=31,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="setpoint_room_cool_night",
        name="Room setpoint cooling (night)",
        address=33,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
    EntityDef(
        key="setpoint_dhw",
        name="User-defined DHW setpoint",
        address=173,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        unit="°C",
    ),
)

SENSORS: dict[str, EntityDef] = {e.key: e for e in _SENSOR_DEFS}
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/entities/sensors.py tests/test_entities.py
git commit -m "feat: add sensor entity definitions"
```

---

### Task 4: Create entities/switches.py

**Files:**
- Create: `~/Github/python-qube-heatpump/src/python_qube_heatpump/entities/switches.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_entities.py`

**Step 1: Write the failing test**

Add to `tests/test_entities.py`:

```python
def test_switch_definitions_exist():
    """Test switch definitions are available."""
    from python_qube_heatpump.entities.switches import SWITCHES

    assert len(SWITCHES) > 0

    # Check specific switches
    assert "bms_summerwinter" in SWITCHES
    entity = SWITCHES["bms_summerwinter"]
    assert entity.platform == Platform.SWITCH
    assert entity.writable is True


def test_all_switches_are_writable():
    """Test all switches are marked as writable."""
    from python_qube_heatpump.entities.switches import SWITCHES

    for key, entity in SWITCHES.items():
        assert entity.writable is True, f"Switch {key} should be writable"
        assert entity.platform == Platform.SWITCH, f"Wrong platform for {key}"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py::test_switch_definitions_exist -v
```

Expected: FAIL

**Step 3: Create switches.py**

```python
# src/python_qube_heatpump/entities/switches.py
"""Switch entity definitions for Qube Heat Pump."""

from .base import EntityDef, InputType, Platform

_SWITCH_DEFS: tuple[EntityDef, ...] = (
    EntityDef(
        key="bms_summerwinter",
        name="Activate summer mode (cooling)",
        address=22,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="tapw_timeprogram_bms_forced",
        name="Activate DHW heating",
        address=23,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="antilegionella_frcstart_ant",
        name="Start Anti-legionella",
        address=45,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="en_plantsetp_compens",
        name="Enable heating curve",
        address=46,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="bms_sgready_a",
        name="SG Ready A",
        address=47,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="bms_sgready_b",
        name="SG Ready B",
        address=48,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
    EntityDef(
        key="modbus_demand",
        name="Activate central heating",
        address=49,
        input_type=InputType.COIL,
        platform=Platform.SWITCH,
        writable=True,
    ),
)

SWITCHES: dict[str, EntityDef] = {e.key: e for e in _SWITCH_DEFS}
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/entities/switches.py tests/test_entities.py
git commit -m "feat: add switch entity definitions"
```

---

### Task 5: Create entities/__init__.py

**Files:**
- Create: `~/Github/python-qube-heatpump/src/python_qube_heatpump/entities/__init__.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_entities.py`

**Step 1: Write the failing test**

Add to `tests/test_entities.py`:

```python
def test_entities_module_exports():
    """Test entities module exports all definitions."""
    from python_qube_heatpump.entities import (
        ALL_ENTITIES,
        BINARY_SENSORS,
        SENSORS,
        SWITCHES,
        DataType,
        EntityDef,
        InputType,
        Platform,
    )

    # Check all exports work
    assert len(SENSORS) > 0
    assert len(BINARY_SENSORS) > 0
    assert len(SWITCHES) > 0

    # Check ALL_ENTITIES contains everything
    total = len(SENSORS) + len(BINARY_SENSORS) + len(SWITCHES)
    assert len(ALL_ENTITIES) == total


def test_no_duplicate_keys():
    """Test no duplicate keys across all entity types."""
    from python_qube_heatpump.entities import BINARY_SENSORS, SENSORS, SWITCHES

    all_keys = list(SENSORS.keys()) + list(BINARY_SENSORS.keys()) + list(SWITCHES.keys())
    assert len(all_keys) == len(set(all_keys)), "Duplicate keys found"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py::test_entities_module_exports -v
```

Expected: FAIL

**Step 3: Create __init__.py**

```python
# src/python_qube_heatpump/entities/__init__.py
"""Entity definitions for Qube Heat Pump.

This module provides all entity definitions that the Home Assistant
integration can use to create sensors, binary sensors, and switches.
"""

from .base import DataType, EntityDef, InputType, Platform
from .binary_sensors import BINARY_SENSORS
from .sensors import SENSORS
from .switches import SWITCHES

# Combined registry of all entities
ALL_ENTITIES: dict[str, EntityDef] = {
    **SENSORS,
    **BINARY_SENSORS,
    **SWITCHES,
}

__all__ = [
    "DataType",
    "EntityDef",
    "InputType",
    "Platform",
    "SENSORS",
    "BINARY_SENSORS",
    "SWITCHES",
    "ALL_ENTITIES",
]
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_entities.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/entities/__init__.py tests/test_entities.py
git commit -m "feat: add entities module with combined exports"
```

---

### Task 6: Update models.py with _extended dict

**Files:**
- Modify: `~/Github/python-qube-heatpump/src/python_qube_heatpump/models.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_client.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
def test_qube_state_get_method():
    """Test QubeState.get() method."""
    from python_qube_heatpump.models import QubeState

    state = QubeState(temp_supply=25.5)

    # Get typed field
    assert state.get("temp_supply") == 25.5

    # Get missing field returns default
    assert state.get("nonexistent") is None
    assert state.get("nonexistent", "default") == "default"


def test_qube_state_extended_dict():
    """Test QubeState._extended dict for additional entities."""
    from python_qube_heatpump.models import QubeState

    state = QubeState()
    state._extended["custom_sensor"] = 42.0

    # Access via get()
    assert state.get("custom_sensor") == 42.0

    # Typed field takes precedence over extended
    state.temp_supply = 25.5
    state._extended["temp_supply"] = 99.9
    assert state.get("temp_supply") == 25.5
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py::test_qube_state_get_method -v
```

Expected: FAIL

**Step 3: Update models.py**

```python
# src/python_qube_heatpump/models.py
"""Models for Qube Heat Pump."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QubeState:
    """Representation of the Qube Heat Pump state.

    Core fields are typed for backward compatibility with the official
    Home Assistant integration. Additional entities use the _extended dict.
    """

    # Temperatures (core - typed for official HA integration)
    temp_supply: float | None = None
    temp_return: float | None = None
    temp_source_in: float | None = None
    temp_source_out: float | None = None
    temp_room: float | None = None
    temp_dhw: float | None = None
    temp_outside: float | None = None

    # Power/Energy (core)
    power_thermic: float | None = None
    power_electric: float | None = None
    energy_total_electric: float | None = None
    energy_total_thermic: float | None = None
    cop_calc: float | None = None

    # Operation (core)
    status_code: int | None = None
    compressor_speed: float | None = None
    flow_rate: float | None = None

    # Setpoints (core)
    setpoint_room_heat_day: float | None = None
    setpoint_room_heat_night: float | None = None
    setpoint_room_cool_day: float | None = None
    setpoint_room_cool_night: float | None = None
    setpoint_dhw: float | None = None

    # Extended data for additional entities (HACS integration)
    _extended: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key, checking typed fields first, then extended.

        Args:
            key: The attribute name to look up.
            default: Value to return if key is not found.

        Returns:
            The value for the key, or default if not found.
        """
        # Check typed fields first (excluding private attributes)
        if hasattr(self, key) and not key.startswith("_"):
            val = getattr(self, key)
            if val is not None:
                return val
        # Fall back to extended dict
        return self._extended.get(key, default)
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/models.py tests/test_client.py
git commit -m "feat: add _extended dict and get() method to QubeState"
```

---

### Task 7: Update const.py with status code mappings

**Files:**
- Modify: `~/Github/python-qube-heatpump/src/python_qube_heatpump/const.py`
- Create: `~/Github/python-qube-heatpump/tests/test_const.py`

**Step 1: Write the failing test**

```python
# tests/test_const.py
"""Tests for constants."""

from python_qube_heatpump.const import STATUS_CODES, get_status_text


def test_status_codes_exist():
    """Test status codes are defined."""
    assert len(STATUS_CODES) > 0
    assert 0 in STATUS_CODES
    assert STATUS_CODES[0] == "standby"


def test_get_status_text():
    """Test get_status_text function."""
    assert get_status_text(0) == "standby"
    assert get_status_text(6) == "heating"
    assert get_status_text(999) == "unknown"
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_const.py -v
```

Expected: FAIL

**Step 3: Update const.py**

```python
# src/python_qube_heatpump/const.py
"""Constants for Qube Heat Pump."""

from enum import Enum


class ModbusType(str, Enum):
    """Modbus register type."""

    HOLDING = "holding"
    INPUT = "input"


class DataType(str, Enum):
    """Data type."""

    FLOAT32 = "float32"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"


# Status code to human-readable text mapping
STATUS_CODES: dict[int, str] = {
    0: "standby",
    1: "alarm",
    2: "keyboard_off",
    3: "compressor_startup",
    4: "compressor_shutdown",
    5: "cooling",
    6: "heating",
    7: "start_fail",
    8: "heating_dhw",
}


def get_status_text(code: int) -> str:
    """Get human-readable status text from status code.

    Args:
        code: The numeric status code from the heat pump.

    Returns:
        Human-readable status string, or "unknown" if code not recognized.
    """
    return STATUS_CODES.get(code, "unknown")


# Register definitions (Address, Type, Data Type, Scale, Offset)
# Kept for backward compatibility with existing get_all_data()
# New code should use entities module instead

PCT_USER_PUMP = (4, ModbusType.INPUT, DataType.FLOAT32, -1, 100)
PCT_SOURCE_PUMP = (6, ModbusType.INPUT, DataType.FLOAT32, -1, 100)
PCT_SOURCE_VALVE = (8, ModbusType.INPUT, DataType.FLOAT32, None, None)
REQ_DHW = (14, ModbusType.INPUT, DataType.FLOAT32, None, None)
REQ_COMPRESSOR = (16, ModbusType.INPUT, DataType.FLOAT32, None, None)
FLOW_RATE = (18, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_SUPPLY = (20, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_RETURN = (22, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_SOURCE_IN = (24, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_SOURCE_OUT = (26, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_ROOM = (28, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_DHW = (30, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_OUTSIDE = (32, ModbusType.INPUT, DataType.FLOAT32, None, None)
COP_CALC = (34, ModbusType.INPUT, DataType.FLOAT32, None, None)
POWER_THERMIC = (36, ModbusType.INPUT, DataType.FLOAT32, None, None)
STATUS_CODE = (38, ModbusType.INPUT, DataType.UINT16, None, None)
TEMP_REG_SETPOINT = (39, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_COOL_SETPOINT = (41, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_HEAT_SETPOINT = (43, ModbusType.INPUT, DataType.FLOAT32, None, None)
COMPRESSOR_SPEED = (45, ModbusType.INPUT, DataType.FLOAT32, 60, None)
TEMP_DHW_SETPOINT = (47, ModbusType.INPUT, DataType.FLOAT32, None, None)
HOURS_DHW = (50, ModbusType.INPUT, DataType.INT16, None, None)
HOURS_HEAT = (52, ModbusType.INPUT, DataType.INT16, None, None)
HOURS_COOL = (54, ModbusType.INPUT, DataType.INT16, None, None)
HOURS_HEATER_1 = (56, ModbusType.INPUT, DataType.INT16, None, None)
HOURS_HEATER_2 = (58, ModbusType.INPUT, DataType.INT16, None, None)
HOURS_HEATER_3 = (60, ModbusType.INPUT, DataType.INT16, None, None)
POWER_ELECTRIC_CALC = (61, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_PLANT_SETPOINT = (65, ModbusType.INPUT, DataType.FLOAT32, None, None)
ENERGY_ELECTRIC_TOTAL = (69, ModbusType.INPUT, DataType.FLOAT32, None, None)
ENERGY_THERMIC_TOTAL = (71, ModbusType.INPUT, DataType.FLOAT32, None, None)
TEMP_ROOM_MODBUS = (75, ModbusType.INPUT, DataType.FLOAT32, None, None)

# Holding registers
SETPOINT_HEAT_DAY = (27, ModbusType.HOLDING, DataType.FLOAT32, None, None)
SETPOINT_HEAT_NIGHT = (29, ModbusType.HOLDING, DataType.FLOAT32, None, None)
SETPOINT_COOL_DAY = (31, ModbusType.HOLDING, DataType.FLOAT32, None, None)
SETPOINT_COOL_NIGHT = (33, ModbusType.HOLDING, DataType.FLOAT32, None, None)
DT_DHW = (43, ModbusType.HOLDING, DataType.INT16, None, None)
MIN_TEMP_DHW = (44, ModbusType.HOLDING, DataType.FLOAT32, None, None)
TEMP_DHW_PROG = (46, ModbusType.HOLDING, DataType.FLOAT32, None, None)
MIN_SETPOINT_BUFFER = (99, ModbusType.HOLDING, DataType.FLOAT32, None, None)
USER_HEAT_SETPOINT = (101, ModbusType.HOLDING, DataType.FLOAT32, None, None)
USER_COOL_SETPOINT = (103, ModbusType.HOLDING, DataType.FLOAT32, None, None)
MAX_SETPOINT_BUFFER = (169, ModbusType.HOLDING, DataType.FLOAT32, None, None)
USER_DHW_SETPOINT = (173, ModbusType.HOLDING, DataType.FLOAT32, None, None)
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_const.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/const.py tests/test_const.py
git commit -m "feat: add status code mappings and get_status_text function"
```

---

### Task 8: Extend client.py with new read methods

**Files:**
- Modify: `~/Github/python-qube-heatpump/src/python_qube_heatpump/client.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_client.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
import pytest
from python_qube_heatpump.entities import SENSORS, BINARY_SENSORS, SWITCHES
from python_qube_heatpump.entities.base import EntityDef, InputType, DataType, Platform


@pytest.mark.asyncio
async def test_read_sensor(mock_modbus_client):
    """Test reading a sensor entity."""
    from python_qube_heatpump import QubeClient

    client = QubeClient("192.168.1.100")
    await client.connect()

    # Mock the response for temp_supply (address 20, FLOAT32)
    mock_modbus_client.return_value.read_input_registers.return_value.registers = [
        0x0000, 0x41C8  # 25.0 in little-endian float32
    ]

    entity = SENSORS["temp_supply"]
    result = await client.read_sensor(entity)

    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_read_binary_sensor(mock_modbus_client):
    """Test reading a binary sensor entity."""
    from python_qube_heatpump import QubeClient

    client = QubeClient("192.168.1.100")
    await client.connect()

    # Mock discrete input response
    mock_modbus_client.return_value.read_discrete_inputs.return_value.bits = [True]

    entity = BINARY_SENSORS["dout_srcpmp_val"]
    result = await client.read_binary_sensor(entity)

    assert result is True


@pytest.mark.asyncio
async def test_read_entities_bulk(mock_modbus_client):
    """Test bulk reading multiple entities."""
    from python_qube_heatpump import QubeClient

    client = QubeClient("192.168.1.100")
    await client.connect()

    # Mock responses
    mock_modbus_client.return_value.read_input_registers.return_value.registers = [
        0x0000, 0x41C8
    ]
    mock_modbus_client.return_value.read_discrete_inputs.return_value.bits = [True]

    entities = [SENSORS["temp_supply"], BINARY_SENSORS["dout_srcpmp_val"]]
    result = await client.read_entities(entities)

    assert "temp_supply" in result
    assert "dout_srcpmp_val" in result
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py::test_read_sensor -v
```

Expected: FAIL with "AttributeError: 'QubeClient' object has no attribute 'read_sensor'"

**Step 3: Update client.py**

Add the new methods to QubeClient (this is a significant update - showing key additions):

```python
# Add to client.py imports
from .entities.base import DataType as EntityDataType, EntityDef, InputType

# Add these methods to QubeClient class:

async def read_sensor(self, entity: EntityDef) -> float | int | None:
    """Read a sensor entity value.

    Args:
        entity: The EntityDef describing the sensor to read.

    Returns:
        The sensor value, or None if read failed.
    """
    if entity.input_type == InputType.INPUT_REGISTER:
        return await self._read_input_register(entity)
    elif entity.input_type == InputType.HOLDING_REGISTER:
        return await self._read_holding_register(entity)
    return None

async def read_binary_sensor(self, entity: EntityDef) -> bool | None:
    """Read a binary sensor entity value.

    Args:
        entity: The EntityDef describing the binary sensor to read.

    Returns:
        The boolean value, or None if read failed.
    """
    if entity.input_type == InputType.DISCRETE_INPUT:
        result = await self._client.read_discrete_inputs(entity.address, 1)
        if result.isError():
            return None
        return result.bits[0]
    elif entity.input_type == InputType.COIL:
        result = await self._client.read_coils(entity.address, 1)
        if result.isError():
            return None
        return result.bits[0]
    return None

async def read_switch_state(self, entity: EntityDef) -> bool | None:
    """Read the current state of a switch entity.

    Args:
        entity: The EntityDef describing the switch to read.

    Returns:
        The boolean state, or None if read failed.
    """
    return await self.read_binary_sensor(entity)

async def read_entities(
    self, entities: list[EntityDef]
) -> dict[str, float | int | bool | None]:
    """Read multiple entities in sequence.

    Args:
        entities: List of EntityDef objects to read.

    Returns:
        Dictionary mapping entity keys to their values.
    """
    result: dict[str, float | int | bool | None] = {}
    for entity in entities:
        if entity.platform == Platform.SENSOR:
            result[entity.key] = await self.read_sensor(entity)
        elif entity.platform == Platform.BINARY_SENSOR:
            result[entity.key] = await self.read_binary_sensor(entity)
        elif entity.platform == Platform.SWITCH:
            result[entity.key] = await self.read_switch_state(entity)
    return result

async def _read_input_register(self, entity: EntityDef) -> float | int | None:
    """Read an input register based on entity definition."""
    count = 2 if entity.data_type in (EntityDataType.FLOAT32, EntityDataType.INT32, EntityDataType.UINT32) else 1
    result = await self._client.read_input_registers(entity.address, count)
    if result.isError():
        return None
    return self._decode_value(result.registers, entity)

async def _read_holding_register(self, entity: EntityDef) -> float | int | None:
    """Read a holding register based on entity definition."""
    count = 2 if entity.data_type in (EntityDataType.FLOAT32, EntityDataType.INT32, EntityDataType.UINT32) else 1
    result = await self._client.read_holding_registers(entity.address, count)
    if result.isError():
        return None
    return self._decode_value(result.registers, entity)

def _decode_value(self, registers: list[int], entity: EntityDef) -> float | int | None:
    """Decode register values based on entity data type."""
    if entity.data_type == EntityDataType.FLOAT32:
        int_val = (registers[1] << 16) | registers[0]
        import struct
        value = struct.unpack(">f", struct.pack(">I", int_val))[0]
    elif entity.data_type == EntityDataType.INT16:
        value = registers[0]
        if value > 32767:
            value -= 65536
    elif entity.data_type == EntityDataType.UINT16:
        value = registers[0]
    elif entity.data_type == EntityDataType.INT32:
        value = (registers[1] << 16) | registers[0]
        if value > 2147483647:
            value -= 4294967296
    elif entity.data_type == EntityDataType.UINT32:
        value = (registers[1] << 16) | registers[0]
    else:
        return None

    # Apply transformations
    if entity.scale is not None:
        value *= entity.scale
    if entity.offset is not None:
        value += entity.offset

    return value
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/client.py tests/test_client.py
git commit -m "feat: add read_sensor, read_binary_sensor, and read_entities methods"
```

---

### Task 9: Add write methods to client.py

**Files:**
- Modify: `~/Github/python-qube-heatpump/src/python_qube_heatpump/client.py`
- Modify: `~/Github/python-qube-heatpump/tests/test_client.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
@pytest.mark.asyncio
async def test_write_switch(mock_modbus_client):
    """Test writing a switch entity."""
    from python_qube_heatpump import QubeClient

    client = QubeClient("192.168.1.100")
    await client.connect()

    mock_modbus_client.return_value.write_coil.return_value.isError.return_value = False

    entity = SWITCHES["bms_summerwinter"]
    await client.write_switch(entity, True)

    mock_modbus_client.return_value.write_coil.assert_called_once_with(22, True)


@pytest.mark.asyncio
async def test_write_setpoint(mock_modbus_client):
    """Test writing a setpoint value."""
    from python_qube_heatpump import QubeClient
    from python_qube_heatpump.entities.base import EntityDef, InputType, DataType, Platform

    client = QubeClient("192.168.1.100")
    await client.connect()

    mock_modbus_client.return_value.write_registers.return_value.isError.return_value = False

    # Create a writable setpoint entity
    entity = EntityDef(
        key="test_setpoint",
        name="Test setpoint",
        address=100,
        input_type=InputType.HOLDING_REGISTER,
        data_type=DataType.FLOAT32,
        platform=Platform.SENSOR,
        writable=True,
    )

    await client.write_setpoint(entity, 25.5)

    mock_modbus_client.return_value.write_registers.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py::test_write_switch -v
```

Expected: FAIL with "AttributeError: 'QubeClient' object has no attribute 'write_switch'"

**Step 3: Add write methods to client.py**

```python
# Add to QubeClient class:

async def write_switch(self, entity: EntityDef, value: bool) -> None:
    """Write a switch entity value.

    Args:
        entity: The EntityDef describing the switch.
        value: The boolean value to write (True = on, False = off).

    Raises:
        ValueError: If entity is not writable or not a coil.
    """
    if not entity.writable:
        raise ValueError(f"Entity {entity.key} is not writable")

    if entity.input_type != InputType.COIL:
        raise ValueError(f"Entity {entity.key} is not a coil, cannot write as switch")

    result = await self._client.write_coil(entity.address, value)
    if result.isError():
        raise IOError(f"Failed to write switch {entity.key}: {result}")

async def write_setpoint(self, entity: EntityDef, value: float) -> None:
    """Write a setpoint value to a holding register.

    Args:
        entity: The EntityDef describing the setpoint.
        value: The numeric value to write.

    Raises:
        ValueError: If entity is not writable or not a holding register.
    """
    if not entity.writable:
        raise ValueError(f"Entity {entity.key} is not writable")

    if entity.input_type != InputType.HOLDING_REGISTER:
        raise ValueError(f"Entity {entity.key} is not a holding register")

    # Encode value based on data type
    registers = self._encode_value(value, entity)

    result = await self._client.write_registers(entity.address, registers)
    if result.isError():
        raise IOError(f"Failed to write setpoint {entity.key}: {result}")

def _encode_value(self, value: float, entity: EntityDef) -> list[int]:
    """Encode a value to register format based on entity data type."""
    import struct

    if entity.data_type == EntityDataType.FLOAT32:
        # Big-endian float to int, then split into little-endian words
        int_val = struct.unpack(">I", struct.pack(">f", value))[0]
        return [int_val & 0xFFFF, (int_val >> 16) & 0xFFFF]
    elif entity.data_type == EntityDataType.INT16:
        if value < 0:
            value = int(value) + 65536
        return [int(value) & 0xFFFF]
    elif entity.data_type == EntityDataType.UINT16:
        return [int(value) & 0xFFFF]
    else:
        raise ValueError(f"Unsupported data type for writing: {entity.data_type}")
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/client.py tests/test_client.py
git commit -m "feat: add write_switch and write_setpoint methods"
```

---

### Task 10: Update __init__.py exports

**Files:**
- Modify: `~/Github/python-qube-heatpump/src/python_qube_heatpump/__init__.py`

**Step 1: Write the failing test**

Add to `tests/test_client.py`:

```python
def test_package_exports():
    """Test package exports all necessary components."""
    from python_qube_heatpump import (
        QubeClient,
        QubeState,
        get_status_text,
        STATUS_CODES,
    )
    from python_qube_heatpump.entities import (
        EntityDef,
        InputType,
        DataType,
        Platform,
        SENSORS,
        BINARY_SENSORS,
        SWITCHES,
        ALL_ENTITIES,
    )

    assert QubeClient is not None
    assert QubeState is not None
    assert get_status_text is not None
    assert len(SENSORS) > 0
```

**Step 2: Run test to verify it fails**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py::test_package_exports -v
```

Expected: Might fail if exports not complete

**Step 3: Update __init__.py**

```python
# src/python_qube_heatpump/__init__.py
"""Python library for Qube Heat Pump communication via Modbus TCP."""

from .client import QubeClient
from .const import STATUS_CODES, get_status_text
from .models import QubeState

__all__ = [
    "QubeClient",
    "QubeState",
    "STATUS_CODES",
    "get_status_text",
]
```

**Step 4: Run test to verify it passes**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/test_client.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd ~/Github/python-qube-heatpump
git add src/python_qube_heatpump/__init__.py tests/test_client.py
git commit -m "feat: update package exports with status code helpers"
```

---

### Task 11: Run all library tests and fix any issues

**Step 1: Run full test suite**

```bash
cd ~/Github/python-qube-heatpump
pytest tests/ -v --cov=python_qube_heatpump --cov-report=term-missing
```

**Step 2: Run linting**

```bash
cd ~/Github/python-qube-heatpump
ruff check src/ tests/
ruff format src/ tests/
```

**Step 3: Fix any issues found**

**Step 4: Commit fixes**

```bash
cd ~/Github/python-qube-heatpump
git add -A
git commit -m "fix: address linting and test issues"
```

---

### Task 12: Update version and prepare release

**Files:**
- Modify: `~/Github/python-qube-heatpump/pyproject.toml`

**Step 1: Update version**

Change version in pyproject.toml from "1.2.3" to "2.0.0"

**Step 2: Commit version bump**

```bash
cd ~/Github/python-qube-heatpump
git add pyproject.toml
git commit -m "chore: bump version to 2.0.0 for entity definitions release"
```

**Step 3: Push changes**

```bash
cd ~/Github/python-qube-heatpump
git push origin main
```

**Note:** Do NOT tag and release yet - wait until integration is tested with local library.

---

## Phase 2: Integration Core

### Task 13: Set up testing infrastructure

**Files:**
- Create: `~/Github/qube_heatpump/pyproject.toml`
- Create: `~/Github/qube_heatpump/.pre-commit-config.yaml`
- Create: `~/Github/qube_heatpump/mypy.ini` (or update existing)

**Step 1: Create/update pyproject.toml**

```toml
[project]
name = "qube-heatpump-hacs"
version = "2.0.0"
description = "HACS integration for Qube Heat Pump"
requires-python = ">=3.12"
dependencies = [
    "python-qube-heatpump>=2.0.0",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "pytest-homeassistant-custom-component>=0.13.0",
]
dev = [
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "pre-commit>=3.7.0",
    "homeassistant-stubs",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
strict = true
```

**Step 2: Create .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - homeassistant-stubs
        files: ^custom_components/
```

**Step 3: Install pre-commit**

```bash
cd ~/Github/qube_heatpump
pip install pre-commit
pre-commit install
```

**Step 4: Commit**

```bash
cd ~/Github/qube_heatpump
git add pyproject.toml .pre-commit-config.yaml
git commit -m "chore: add testing infrastructure and pre-commit hooks"
```

---

## Remaining Tasks (Summary)

Due to the length of this plan, the remaining tasks are summarized. Each follows the same TDD pattern:

### Phase 2 (continued): Integration Core
- **Task 14**: Create `const.py` with DOMAIN, PLATFORMS, defaults
- **Task 15**: Create `hub.py` wrapping QubeClient
- **Task 16**: Create `coordinator.py` with DataUpdateCoordinator
- **Task 17**: Create `entity.py` with base QubeEntity class
- **Task 18**: Update `__init__.py` with setup/unload
- **Task 19**: Simplify `config_flow.py` (remove options flow)
- **Task 20**: Update `manifest.json` with new version/requirements

### Phase 3: Platforms
- **Task 21**: Implement `sensor.py` with entity descriptions
- **Task 22**: Implement `binary_sensor.py`
- **Task 23**: Implement `switch.py`
- **Task 24**: Implement `button.py` (reload button)
- **Task 25**: Implement `select.py` (SG Ready mode)

### Phase 4: Services & Computed
- **Task 26**: Add entity-based action services
- **Task 27**: Implement computed sensors (standby, status)
- **Task 28**: Implement SCOP calculations (if needed)

### Phase 5: Polish
- **Task 29**: Update translations (en.json, nl.json)
- **Task 30**: Set up GitHub Actions CI
- **Task 31**: Run hassfest validation
- **Task 32**: Run HACS validation
- **Task 33**: Final testing and documentation

---

## Success Criteria

- [ ] Library v2.0.0 released with entity definitions
- [ ] All 89 entities available via library
- [ ] All platforms working: sensor, binary_sensor, switch, button, select
- [ ] Test coverage >90%
- [ ] Passes `ruff check` and `ruff format --check`
- [ ] Passes `mypy` type checking
- [ ] Passes hassfest validation
- [ ] Passes HACS validation
- [ ] English + Dutch translations complete
- [ ] Entity-based action services working
