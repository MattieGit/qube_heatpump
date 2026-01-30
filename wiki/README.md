# Qube Heat Pump Wiki

## Table of Contents

1. [Version 2.0.0 Breaking Changes](#version-200-breaking-changes)
2. [Entity Reference](#entity-reference)
3. [Computed & Derived Entities](#computed--derived-entities)
4. [SG Ready Signals](#sg-ready-signals)
5. [Virtual Thermostat Control](#virtual-thermostat-control)
6. [Dashboard Controls](#dashboard-controls)
7. [Data Integrity & Monotonic Clamping](#data-integrity--monotonic-clamping)
8. [Error Handling & Recovery](#error-handling--recovery)
9. [Security Considerations](#security-considerations)
10. [Diagnostics Toolkit](#diagnostics-toolkit)
11. [Migration from v1.x](#migration-from-v1x)

---

## Version 2.0.0 Breaking Changes

Version 2.0.0 is a major architectural update that prepares the integration for eventual inclusion in Home Assistant core. This is a **breaking release** that requires manual migration.

### Architecture Changes

| Component | v1.x | v2.0.0 |
|-----------|------|--------|
| Entity definitions | `modbus.yaml` file | [python-qube-heatpump](https://pypi.org/project/python-qube-heatpump/) library |
| Coordination | Custom polling | `DataUpdateCoordinator` pattern |
| Entity naming | Mixed Dutch/English | Consistent English keys with translations |
| Setpoint control | `write_register` service | Native `number` entities |
| Multi-device | Custom labels in options | Single device per config entry |

### Why These Changes?

1. **Official HA patterns** - Using `DataUpdateCoordinator` and entity descriptions aligns with HA core requirements
2. **Maintainability** - Entity definitions in a separate PyPI library can be versioned and tested independently
3. **Type safety** - Python dataclasses with type hints replace untyped YAML
4. **Translation support** - Proper HA translation system instead of custom entity naming

---

## Entity Reference

### Sensors (50+)

The integration exposes all readable Modbus registers as sensors:

| Category | Examples |
|----------|----------|
| **Temperatures** | `sensor.outtemp`, `sensor.supplytemp`, `sensor.rettemp`, `sensor.dhw_temp`, `sensor.roomtemp` |
| **Power** | `sensor.generalmng_eletricpwr`, `sensor.generalmng_thermic_pwr` |
| **Energy** | `sensor.generalmng_acumulatedpwr`, `sensor.generalmng_acumulatedthermic` |
| **Setpoints** | `sensor.heatsetp_1`, `sensor.coolsetp_1`, `sensor.dhw_setp`, `sensor.regsetp` |
| **Operating hours** | `sensor.workinghours_dhw_hrsret`, `sensor.workinghours_heat_hrsret`, `sensor.workinghours_cool_hrsret` |
| **Diagnostics** | `sensor.qube_info`, `sensor.qube_ip_address`, `sensor.qube_metric_errors_connect` |

### Binary Sensors (37)

| Category | Examples |
|----------|----------|
| **Alarms** | `binary_sensor.glbal`, `binary_sensor.usralrms`, `binary_sensor.alrm_flw` |
| **Valve outputs** | `binary_sensor.dout_threewayvlv_val`, `binary_sensor.dout_fourwayvlv_val` |
| **Pump outputs** | `binary_sensor.dout_srcpmp_val`, `binary_sensor.dout_usrpmp_val` |
| **Heater outputs** | `binary_sensor.dout_heaterstep1_val`, `binary_sensor.dout_heaterstep2_val` |
| **Digital inputs** | `binary_sensor.dewpoint`, `binary_sensor.srcflw`, `binary_sensor.id_demand` |
| **Status** | `binary_sensor.bms_demand`, `binary_sensor.surplus_pv`, `binary_sensor.daynightmode` |

### Switches (7)

| Entity | Description |
|--------|-------------|
| `switch.bms_summerwinter` | Enable summer/cooling mode |
| `switch.tapw_timeprogram_bms_forced` | Force DHW heating |
| `switch.antilegionella_frcstart_ant` | Start anti-legionella cycle |
| `switch.en_plantsetp_compens` | Enable heating curve |
| `switch.modbus_demand` | Trigger heat demand |
| `switch.bms_sgready_a` | SG Ready signal A (hidden) |
| `switch.bms_sgready_b` | SG Ready signal B (hidden) |

### Number Entities (2)

| Entity | Description | Range |
|--------|-------------|-------|
| `number.setpoint_dhw` | DHW temperature setpoint | 40-60°C |
| `number.tapw_timeprogram_dhwsetp_nolinq` | User-defined DHW setpoint | 40-60°C |

### Select Entity (1)

| Entity | Options |
|--------|---------|
| `select.sgready_mode` | Off, Block, Plus, Max |

---

## Computed & Derived Entities

Beyond raw Modbus registers, the integration creates several computed sensors:

### Energy Tracking

| Entity | Description |
|--------|-------------|
| `sensor.qube_standby_power` | Fixed 17W standby power |
| `sensor.qube_standby_energy` | Accumulated standby consumption (kWh) |
| `sensor.qube_total_energy_with_standby` | Total consumption including standby |
| `sensor.qube_energy_tariff_cv` | Monthly CV electrical consumption |
| `sensor.qube_energy_tariff_sww` | Monthly SWW electrical consumption |
| `sensor.thermische_opbrengst_maand` | Monthly total thermal yield |
| `sensor.thermische_opbrengst_cv_maand` | Monthly CV thermal yield |
| `sensor.thermische_opbrengst_sww_maand` | Monthly SWW thermal yield |

### SCOP Calculations

| Entity | Period | Scope |
|--------|--------|-------|
| `sensor.scop_maand` | Monthly | Total |
| `sensor.scop_cv_maand` | Monthly | CV only |
| `sensor.scop_sww_maand` | Monthly | SWW only |
| `sensor.scop_dag` | Daily | Total |
| `sensor.scop_cv_dag` | Daily | CV only |
| `sensor.scop_sww_dag` | Daily | SWW only |

SCOP values are calculated by dividing thermal yield by electrical consumption. Values outside the 0-10 range are filtered as implausible.

### Status Sensors

| Entity | Values |
|--------|--------|
| `sensor.status_heatpump` | standby, alarm, keyboard_off, compressor_startup, compressor_shutdown, cooling, heating, start_fail, heating_dhw, unknown |
| `sensor.drieweg_status` | dhw, cv |
| `sensor.vierweg_status` | heating, cooling |

---

## SG Ready Signals

The heat pump supports SG Ready signals for smart grid integration. The `select.sgready_mode` entity provides a user-friendly interface:

| Mode | SG Ready A | SG Ready B | Behavior |
|------|------------|------------|----------|
| **Off** | Off | Off | Normal operation |
| **Block** | On | Off | Block heat pump operation |
| **Plus** | Off | On | Regular heating curve, room +1K, DHW day mode |
| **Max** | On | On | Anti-legionella once, surplus curve, room +1K |

The underlying `switch.bms_sgready_a` and `switch.bms_sgready_b` entities are hidden by default but remain available for advanced automations.

---

## Virtual Thermostat Control

To control the Qube from Home Assistant instead of the built-in Linq thermostat:

### 1. Disable Linq Thermostat Options

On the heat pump controller, disable:
- Room temperature control via Linq
- DHW control via Linq

![Qube Linq thermostat configuration](../assets/qube_heatpump_settings.png)

### 2. Use Modbus Demand Switch

```yaml
automation:
  - alias: "Thermostat heat demand"
    trigger:
      - platform: state
        entity_id: climate.your_thermostat
        attribute: hvac_action
        to: "heating"
    action:
      - service: switch.turn_on
        entity_id: switch.modbus_demand

  - alias: "Thermostat demand off"
    trigger:
      - platform: state
        entity_id: climate.your_thermostat
        attribute: hvac_action
        to: "idle"
    action:
      - service: switch.turn_off
        entity_id: switch.modbus_demand
```

### 3. Control DHW Setpoint (v2.0.0)

Use the native number entity:

```yaml
service: number.set_value
target:
  entity_id: number.setpoint_dhw
data:
  value: 52
```

---

## Dashboard Controls

The sample dashboard in `examples/dashboard_qube_overview.yaml` includes:

- **System snapshot** - Picture elements with temperature overlays
- **Controls** - Switches for summer mode, DHW boost, heating curve, SG Ready
- **Demand status** - Heat demand and PV surplus indicators
- **Alarm panel** - Filtered view showing only active alarms
- **Operating hours** - DHW, heating, cooling, heater run times
- **Temperature tiles** - All temperature sensors and setpoints
- **Power & energy** - Current power and accumulated consumption
- **Performance** - Compressor speed, flow, COP, status
- **Diagnostics** - Integration info and error counters

---

## Data Integrity & Monotonic Clamping

The Qube heat pump occasionally reports glitched values for energy counters - values that are lower than the previously reported total. For `total_increasing` sensors, this would corrupt Home Assistant's energy statistics.

The integration implements **monotonic clamping**:

1. For each `total_increasing` sensor, the coordinator tracks the last valid value
2. When a new value arrives that is lower than the previous value, it is rejected
3. The previous valid value is retained
4. A debug log message is recorded for troubleshooting

This applies to:
- All sensors with `state_class: total_increasing`
- Working hours counters (`workinghours_*`)
- Energy accumulation sensors (`generalmng_acumulatedpwr`, `generalmng_acumulatedthermic`)

To view clamping events, enable debug logging:

```yaml
logger:
  logs:
    custom_components.qube_heatpump.coordinator: debug
```

---

## Error Handling & Recovery

- **Exponential backoff** - Connection failures use exponential backoff to prevent log spam
- **Graceful degradation** - Read failures increment counters; entities show `unavailable` until recovery
- **Coordinator pattern** - `DataUpdateCoordinator` handles polling, retries, and state updates
- **Connection persistence** - The Modbus connection is maintained between polls when possible

---

## Security Considerations

### Network Security

Modbus/TCP is an **unencrypted protocol** with no authentication. The integration assumes:

- The heat pump is on a trusted local network
- Network-level access control (firewall, VLAN) is in place if needed
- No sensitive data beyond operational parameters is transmitted

### Write Access

The integration provides two ways to write values:

1. **Entity actions (recommended)** - Use `number.set_value` for setpoints, `switch.turn_on/off` for controls
2. **write_register service (advanced)** - Raw register writes for debugging or custom automations

The `write_register` service can write to any Modbus register. Only use it if you understand the register map.

### No External Connections

All communication is local:
- Direct Modbus/TCP to heat pump IP
- No cloud services or external APIs
- No data leaves your network

---

## Diagnostics Toolkit

### Built-in Diagnostics

1. Go to **Settings → Devices & Services → Qube Heat Pump**
2. Click the three-dot menu → **Download diagnostics**
3. The JSON file includes:
   - Hub configuration
   - Resolved IP address
   - Error counters
   - Entity counts

### Modbus Probe Tool

For low-level debugging, use `modbus_probe.py`:

```bash
python3 /config/custom_components/qube_heatpump/modbus_probe.py \
    --host 192.168.1.100 \
    --unit 1 \
    --address 32 \
    --kind input \
    --data-type float32
```

Options:
- `--kind`: `input`, `holding`, `coil`, `discrete`
- `--data-type`: `uint16`, `int16`, `float32`
- `--word-order`, `--byte-order`: Test endianness variants

---

## Migration from v1.x

### Step 1: Document Current Setup

Before upgrading, note:
- Which entities you use in automations
- Dashboard entity IDs
- Any custom configurations

### Step 2: Remove Old Integration

1. Go to **Settings → Devices & Services**
2. Find Qube Heat Pump and click **Delete**
3. Restart Home Assistant

### Step 3: Install v2.0.0

1. Update via HACS or manual install
2. Restart Home Assistant
3. Add the integration fresh

### Step 4: Update Automations

Replace old entity IDs and service calls:

```yaml
# Old
service: qube_heatpump.write_register
data:
  address: 173
  value: 52
  data_type: float32

# New
service: number.set_value
target:
  entity_id: number.setpoint_dhw
data:
  value: 52
```

### Step 5: Update Dashboards

Use the updated `examples/dashboard_qube_overview.yaml` as reference.

### Key Entity ID Changes

| Old (v1.x) | New (v2.0.0) |
|------------|--------------|
| `sensor.status_warmtepomp` | `sensor.status_heatpump` |
| `sensor.standby_verbruik` | `sensor.qube_standby_energy` |
| `sensor.qube_total_energy_incl_standby` | `sensor.qube_total_energy_with_standby` |
| `sensor.elektrisch_verbruik_cv_maand` | `sensor.qube_energy_tariff_cv` |
| `sensor.elektrisch_verbruik_sww_maand` | `sensor.qube_energy_tariff_sww` |
| `sensor.driewegklep_ssw_cv_status` | `sensor.drieweg_status` |
| `sensor.vierwegklep_verwarmen_koelen_status` | `sensor.vierweg_status` |

### Energy Statistics

After migration, energy statistics will start fresh. Historical data from v1.x cannot be automatically migrated due to entity ID changes.
