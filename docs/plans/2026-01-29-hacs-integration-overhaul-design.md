# HACS Integration Overhaul Design

**Date**: 2026-01-29
**Status**: Approved
**Goal**: Update HACS integration to use official HA architecture patterns and the `python-qube-heatpump` library, enabling smooth transition to official HA integration.

---

## Overview

This design covers updating the Qube Heat Pump HACS integration to:
1. Use the `python-qube-heatpump` library for all device communication
2. Adopt official Home Assistant architecture patterns
3. Support all platforms: sensor, binary_sensor, switch, button, select
4. Maintain a clear path for transitioning to official HA integration

### Related Repositories

| Repository | Path | Purpose |
|------------|------|---------|
| python-qube-heatpump | `~/Github/python-qube-heatpump` | PyPI library for Modbus communication |
| HACS integration | `~/Github/qube_heatpump` | This integration (target of overhaul) |
| Official HA integration | `~/Github/core/homeassistant/components/qube_heatpump/` | Reference for patterns |

---

## Part 1: Library Updates (`python-qube-heatpump`)

### 1.1 New File Structure

```
src/python_qube_heatpump/
├── __init__.py              # Exports QubeClient, EntityDef, enums, entity registries
├── client.py                # QubeClient with extended API
├── models.py                # QubeState with _extended dict
├── const.py                 # Status code mappings, constants
└── entities/
    ├── __init__.py          # Exports SENSORS, BINARY_SENSORS, SWITCHES, ALL_ENTITIES
    ├── base.py              # EntityDef dataclass, InputType, DataType, Platform enums
    ├── sensors.py           # ~300 sensor EntityDef instances
    ├── binary_sensors.py    # ~50 binary sensor EntityDef instances
    └── switches.py          # ~20 switch EntityDef instances
```

### 1.2 EntityDef Dataclass

```python
from dataclasses import dataclass
from enum import Enum

class InputType(str, Enum):
    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"
    INPUT_REGISTER = "input"
    HOLDING_REGISTER = "holding"

class DataType(str, Enum):
    FLOAT32 = "float32"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"

class Platform(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    SWITCH = "switch"

@dataclass(frozen=True)
class EntityDef:
    """Definition of a Qube heat pump entity."""

    # Identity
    key: str                              # Unique identifier, e.g., "temp_supply"
    name: str                             # Human-readable name

    # Modbus specifics
    address: int                          # Register/coil address
    input_type: InputType                 # How to read from device
    data_type: DataType | None = None     # None for coils/discrete inputs

    # Platform hint
    platform: Platform = Platform.SENSOR

    # Value transformation
    scale: float | None = None
    offset: float | None = None

    # Unit (protocol-level)
    unit: str | None = None               # "°C", "kWh", "W", "%", "L/min"

    # Write capability
    writable: bool = False
```

### 1.3 QubeState Model

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class QubeState:
    """State of the Qube Heat Pump."""

    # Core sensors (official HA integration uses these directly)
    temp_supply: float | None = None
    temp_return: float | None = None
    temp_source_in: float | None = None
    temp_source_out: float | None = None
    temp_room: float | None = None
    temp_dhw: float | None = None
    temp_outside: float | None = None
    power_thermic: float | None = None
    power_electric: float | None = None
    energy_total_electric: float | None = None
    energy_total_thermic: float | None = None
    cop_calc: float | None = None
    status_code: int | None = None
    compressor_speed: float | None = None
    flow_rate: float | None = None
    setpoint_room_heat_day: float | None = None
    setpoint_room_heat_night: float | None = None
    setpoint_room_cool_day: float | None = None
    setpoint_room_cool_night: float | None = None
    setpoint_dhw: float | None = None

    # Extended data for additional entities
    _extended: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key, checking typed fields first, then extended."""
        if hasattr(self, key) and not key.startswith('_'):
            val = getattr(self, key)
            if val is not None:
                return val
        return self._extended.get(key, default)
```

### 1.4 QubeClient API

```python
class QubeClient:
    """Async client for Qube Heat Pump communication."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    # Backward compatible
    async def get_all_data(self) -> QubeState: ...

    # Type-specific reads
    async def read_sensor(self, entity: EntityDef) -> float | int | None: ...
    async def read_binary_sensor(self, entity: EntityDef) -> bool | None: ...
    async def read_switch_state(self, entity: EntityDef) -> bool | None: ...

    # Bulk read
    async def read_entities(self, entities: list[EntityDef]) -> dict[str, Any]: ...

    # Writes
    async def write_switch(self, entity: EntityDef, value: bool) -> None: ...
    async def write_setpoint(self, entity: EntityDef, value: float) -> None: ...
```

### 1.5 Status Code Mappings

Library provides device-specific status mappings:

```python
# In const.py
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
    """Get human-readable status from code."""
    return STATUS_CODES.get(code, "unknown")
```

---

## Part 2: HACS Integration Updates

### 2.1 New File Structure

```
custom_components/qube_heatpump/
├── __init__.py              # Setup, QubeData runtime dataclass
├── config_flow.py           # User/reconfigure flows (simplified, no options flow)
├── coordinator.py           # DataUpdateCoordinator
├── hub.py                   # QubeHub wrapper around QubeClient
├── const.py                 # DOMAIN, PLATFORMS, defaults
├── sensor.py                # Sensor platform
├── binary_sensor.py         # Binary sensor platform
├── switch.py                # Switch platform
├── button.py                # Button platform (reload)
├── select.py                # Select platform (SG Ready mode)
├── entity.py                # Base QubeEntity class
├── icons.json               # Icon mappings
├── manifest.json            # Integration metadata
├── strings.json             # English translations
├── services.yaml            # Service definitions (entity-based actions)
├── quality_scale.yaml       # Bronze compliance
└── translations/
    ├── en.json              # English
    └── nl.json              # Dutch
```

### 2.2 Entity Description Pattern

Each platform uses HA's entity description pattern:

```python
# sensor.py
from dataclasses import dataclass
from homeassistant.components.sensor import SensorEntityDescription, SensorDeviceClass
from python_qube_heatpump.entities import EntityDef

@dataclass(frozen=True, kw_only=True)
class QubeSensorEntityDescription(SensorEntityDescription):
    """Qube sensor entity description."""
    entity_def: EntityDef

SENSOR_DESCRIPTIONS: tuple[QubeSensorEntityDescription, ...] = (
    QubeSensorEntityDescription(
        key="temp_supply",
        entity_def=SENSORS["temp_supply"],  # From library
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        translation_key="temp_supply",
    ),
    # ... more sensors
)
```

### 2.3 Coordinator Pattern

```python
class QubeCoordinator(DataUpdateCoordinator[QubeState]):
    """Coordinator for Qube Heat Pump data."""

    def __init__(self, hass: HomeAssistant, hub: QubeHub, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.hub = hub

    async def _async_update_data(self) -> QubeState:
        """Fetch data from device."""
        try:
            return await self.hub.async_get_all_data()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err
```

### 2.4 Base Entity Class

```python
class QubeEntity(CoordinatorEntity[QubeCoordinator]):
    """Base class for Qube entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: QubeCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}-{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.hub.device_id)},
            name="Qube Heat Pump",
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=self.coordinator.hub.version,
        )
```

### 2.5 Computed Entities

Integration handles time-based computations:

- `QubeStandbyPowerSensor` - Static 17W
- `QubeStandbyEnergySensor` - Accumulated using `RestoreSensor`
- `QubeTotalEnergySensor` - Sum of device + standby
- `QubeStatusSensor` - Uses library's `get_status_text()`
- `QubeScopSensor` - Calculated from energy values (monthly/daily)

### 2.6 Services (Entity-Based Actions)

Replace raw `write_register` with entity-based actions:

```yaml
# services.yaml
set_dhw_setpoint:
  name: Set DHW setpoint
  description: Set the domestic hot water setpoint temperature
  fields:
    temperature:
      name: Temperature
      description: Target temperature in °C
      required: true
      selector:
        number:
          min: 40
          max: 60
          step: 0.5
          unit_of_measurement: °C

set_heating_setpoint:
  name: Set heating setpoint
  description: Set the room heating setpoint temperature
  # ... similar structure
```

### 2.7 Removed Features

- Multi-device labels (use HA's native device naming)
- Options flow customization (simplified config)
- Raw `write_register` service (replaced with entity actions)
- YAML-based entity definitions (replaced with library dataclasses)

---

## Part 3: Testing Infrastructure

### 3.1 Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_config_flow.py      # Config flow tests
├── test_init.py             # Setup/unload tests
├── test_coordinator.py      # Coordinator tests
├── test_sensor.py           # Sensor platform tests
├── test_binary_sensor.py    # Binary sensor tests
├── test_switch.py           # Switch tests
├── test_button.py           # Button tests
├── test_select.py           # Select tests
├── test_services.py         # Service tests
└── test_integration.py      # End-to-end tests
```

### 3.2 Tools and Checks

| Tool | Purpose | Command |
|------|---------|---------|
| pytest | Unit/integration tests | `pytest tests/ -v --cov` |
| ruff | Linting + formatting | `ruff check . && ruff format --check .` |
| mypy | Type checking | `mypy custom_components/qube_heatpump` |
| hassfest | HA validation | `python -m script.hassfest` or Docker |
| hacs/action | HACS validation | GitHub Action |
| pre-commit | Git hooks | `pre-commit run --all-files` |

### 3.3 Pre-commit Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [homeassistant-stubs]
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest tests/ -v --tb=short
        language: system
        pass_filenames: false
```

### 3.4 GitHub Actions CI

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[test]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy custom_components/qube_heatpump
      - run: pytest tests/ -v --cov --cov-report=xml

  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
```

---

## Part 4: Migration

### 4.1 Breaking Changes

This is a **clean break** - existing entity IDs will change. Users need to:
1. Update automations referencing old entity IDs
2. Update dashboard cards
3. Update any scripts using old entity IDs

### 4.2 Migration Helper (Nice-to-Have)

Future enhancement: A service or script that:
1. Reads old entity registry
2. Maps old IDs to new IDs
3. Outputs a migration guide or automations patch

### 4.3 Version Bump

Major version bump to indicate breaking changes:
- Library: `python-qube-heatpump` 2.0.0
- Integration: Update `manifest.json` version

---

## Part 5: Translations

### 5.1 Supported Languages

- English (en) - Primary
- Dutch (nl) - Existing translations preserved

### 5.2 Translation Structure

```json
{
  "config": {
    "step": { ... },
    "error": { ... },
    "abort": { ... }
  },
  "entity": {
    "sensor": {
      "temp_supply": { "name": "Supply temperature" },
      ...
    },
    "binary_sensor": { ... },
    "switch": { ... }
  },
  "services": { ... }
}
```

---

## Implementation Order

### Phase 1: Library Updates
1. Add `entities/` module with EntityDef and all definitions
2. Extend QubeClient with new read/write methods
3. Update QubeState with `_extended` dict
4. Add status code mappings
5. Update tests
6. Release as 2.0.0

### Phase 2: Integration Core
1. Set up new file structure
2. Implement coordinator and hub
3. Implement base entity class
4. Set up testing infrastructure

### Phase 3: Platforms
1. Implement sensor platform
2. Implement binary_sensor platform
3. Implement switch platform
4. Implement button platform
5. Implement select platform

### Phase 4: Services & Computed
1. Implement entity-based action services
2. Implement computed entities (standby, SCOP, etc.)

### Phase 5: Polish
1. Translations (en + nl)
2. Documentation
3. CI/CD setup
4. hassfest/HACS validation
5. Testing and coverage

---

## Success Criteria

- [ ] All ~400 entities available via library
- [ ] All platforms working: sensor, binary_sensor, switch, button, select
- [ ] Test coverage >90%
- [ ] Passes hassfest validation
- [ ] Passes HACS validation
- [ ] English + Dutch translations complete
- [ ] Entity-based action services working
- [ ] Clean transition path to official HA documented
