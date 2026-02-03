# Qube Heat Pump Wiki

## Table of Contents

1. [Supported Devices](#supported-devices)
2. [Data Updates](#data-updates)
3. [Known Limitations](#known-limitations)
4. [Entity Reference](#entity-reference)
5. [Computed & Derived Entities](#computed--derived-entities)
6. [SG Ready Signals](#sg-ready-signals)
7. [Virtual Thermostat Control](#virtual-thermostat-control)
8. [Multi-Device Configuration](#multi-device-configuration)
9. [Use Cases](#use-cases)
10. [Dashboard Controls](#dashboard-controls)
11. [Data Integrity & Monotonic Clamping](#data-integrity--monotonic-clamping)
12. [Error Handling & Recovery](#error-handling--recovery)
13. [Security Considerations](#security-considerations)
14. [Troubleshooting](#troubleshooting)
15. [Diagnostics Toolkit](#diagnostics-toolkit)
16. [Notes](#notes)

---

## Supported Devices

This integration supports [Qube](https://qube-renewables.com/) heat pumps with Modbus/TCP connectivity.

### Compatible Models

| Model | Modbus Support | Notes |
|-------|---------------|-------|
| Qube Heat Pump (all variants) | ✅ | Primary supported device |
| Qube with Linq thermostat | ✅ | Can disable Linq for HA control |

### Requirements

- Qube heat pump connected to local network via Ethernet
- Modbus/TCP enabled on the heat pump
- Network access from Home Assistant to heat pump IP (default port: 502)

### Firmware Compatibility

The integration is tested with current Qube firmware versions. If you encounter issues with a specific firmware version, please open an issue on GitHub with your firmware version and the problem description.

---

## Data Updates

### Polling Interval

The integration polls the heat pump every **10 seconds** by default. This interval provides a good balance between responsiveness and network load.

The polling is handled by Home Assistant's `DataUpdateCoordinator` pattern, which:
- Polls all Modbus registers in a single coordinated update
- Handles retry logic automatically
- Makes entity state changes available simultaneously

### When Data Updates

- **On startup**: Initial data fetch when the integration loads
- **Every 10 seconds**: Regular polling interval
- **After writes**: Immediate refresh when you change a setpoint or switch

### Manual Refresh

To force an immediate data refresh:
1. Use the **Reload** button entity (`button.qube_reload`)
2. Or reload the integration from Settings → Devices & Services

---

## Known Limitations

### Technical Limitations

| Limitation | Description | Workaround |
|------------|-------------|------------|
| **Single device per entry** | Each integration entry connects to one heat pump | Add multiple entries for multiple pumps |
| **No auto-discovery** | Modbus devices cannot be auto-discovered | Manual IP configuration required |
| **Fixed register map** | Entity list is determined at setup | Reload integration if registers change |
| **Unencrypted protocol** | Modbus/TCP has no encryption | Keep heat pump on trusted network |
| **No authentication** | Modbus has no user/password | Rely on network-level access control |

### Data Limitations

| Limitation | Description | Notes |
|------------|-------------|-------|
| **Energy counter glitches** | Heat pump occasionally reports invalid energy values | Handled by monotonic clamping (see below) |
| **Entity ID changes** | Changing the entity prefix changes entity IDs | Update automations/dashboards after change |
| **10-second resolution** | Data is polled every 10 seconds | Sub-second changes may be missed |

### Not Supported

- Remote/cloud access (local only)
- Heat pump firmware updates
- Advanced configuration of heat pump parameters beyond exposed registers

---

---

## Entity Reference

All entity IDs include a configurable prefix (default: `qube`) for clear identification. The prefix can be customized via the integration's Options.

### Sensors

The integration exposes all readable Modbus registers as sensors:

| Category | Examples |
|----------|----------|
| **Temperatures** | `sensor.qube_temp_outside`, `sensor.qube_temp_supply`, `sensor.qube_temp_return`, `sensor.qube_temp_dhw`, `sensor.qube_temp_room` |
| **Power** | `sensor.qube_power_electric`, `sensor.qube_power_thermic` |
| **Energy** | `sensor.qube_energy_total_electric`, `sensor.qube_energy_total_thermic` |
| **Setpoints** | `sensor.qube_heatsetp_1`, `sensor.qube_coolsetp_1`, `sensor.qube_dhw_setp`, `sensor.qube_regsetp` |
| **Operating hours** | `sensor.qube_workinghours_dhw_hrsret`, `sensor.qube_workinghours_heat_hrsret`, `sensor.qube_workinghours_cool_hrsret` |
| **Diagnostics** | `sensor.qube_info`, `sensor.qube_ip_address`, `sensor.qube_metric_errors_connect` |

### Binary Sensors

| Category | Examples |
|----------|----------|
| **Alarms** | `binary_sensor.qube_glbal`, `binary_sensor.qube_usralrms`, `binary_sensor.qube_alrm_flw` |
| **Valve outputs** | `binary_sensor.qube_dout_threewayvlv_val`, `binary_sensor.qube_dout_fourwayvlv_val` |
| **Pump outputs** | `binary_sensor.qube_dout_srcpmp_val`, `binary_sensor.qube_dout_usrpmp_val` |
| **Heater outputs** | `binary_sensor.qube_dout_heaterstep1_val`, `binary_sensor.qube_dout_heaterstep2_val` |
| **Digital inputs** | `binary_sensor.qube_dewpoint`, `binary_sensor.qube_srcflw`, `binary_sensor.qube_id_demand` |
| **Status** | `binary_sensor.qube_bms_demand`, `binary_sensor.qube_surplus_pv`, `binary_sensor.qube_daynightmode` |

### Switches

| Entity | Description |
|--------|-------------|
| `switch.qube_modbus_demand` | Trigger heat demand |
| `switch.qube_bms_summerwinter` | Enable summer/cooling mode |
| `switch.qube_tapw_timeprogram_bms_forced` | Force DHW heating |
| `switch.qube_antilegionella_frcstart_ant` | Start anti-legionella cycle |
| `switch.qube_en_plantsetp_compens` | Enable heating curve |

### Number Entities

| Entity | Description | Range |
|--------|-------------|-------|
| `number.qube_tapw_timeprogram_dhwsetp_nolinq_setpoint` | DHW temperature setpoint (manual) | 20-65°C |

### Select Entity

| Entity | Options |
|--------|---------|
| `select.qube_sgready_mode` | Off, Block, Plus, Max |

---

## Computed & Derived Entities

Beyond raw Modbus registers, the integration creates several computed sensors. All entities include the configured prefix (default: `qube`).

### Energy Tracking

#### Monthly Energy Sensors

| Entity | Description |
|--------|-------------|
| `sensor.qube_standby_power` | Fixed 17W standby power |
| `sensor.qube_standby_energy` | Accumulated standby consumption (kWh) |
| `sensor.qube_total_energy_incl_standby` | Total consumption including standby |
| `sensor.qube_electric_consumption_ch_month` | Monthly CH (Central Heating) electrical consumption |
| `sensor.qube_electric_consumption_dhw_month` | Monthly DHW (Domestic Hot Water) electrical consumption |
| `sensor.qube_thermic_yield_month` | Monthly total thermal yield |
| `sensor.qube_thermic_yield_ch_month` | Monthly CH thermal yield |
| `sensor.qube_thermic_yield_dhw_month` | Monthly DHW thermal yield |

#### Daily Energy Sensors

| Entity | Description |
|--------|-------------|
| `sensor.qube_electric_consumption_day` | Daily total electrical consumption |
| `sensor.qube_electric_consumption_ch_day` | Daily CH electrical consumption |
| `sensor.qube_electric_consumption_dhw_day` | Daily DHW electrical consumption |
| `sensor.qube_thermic_yield_day` | Daily total thermal yield |
| `sensor.qube_thermic_yield_ch_day` | Daily CH thermal yield |
| `sensor.qube_thermic_yield_dhw_day` | Daily DHW thermal yield |

Daily sensors reset at midnight (local time). Use these for daily statistics and energy dashboards.

### SCOP Calculations

| Entity | Period | Scope |
|--------|--------|-------|
| `sensor.qube_scop_month` | Monthly | Total |
| `sensor.qube_scop_ch_month` | Monthly | CH only |
| `sensor.qube_scop_dhw_month` | Monthly | DHW only |
| `sensor.qube_scop_day` | Daily | Total |
| `sensor.qube_scop_ch_day` | Daily | CH only |
| `sensor.qube_scop_dhw_day` | Daily | DHW only |

SCOP values are calculated by dividing thermal yield by electrical consumption. Values outside the 0-10 range are filtered as implausible.

### Status Sensors

| Entity | Values |
|--------|--------|
| `sensor.qube_status_heatpump` | standby, alarm, keyboard_off, compressor_startup, compressor_shutdown, cooling, heating, start_fail, heating_dhw, unknown |
| `sensor.qube_drieweg_status` | dhw, ch |
| `sensor.qube_vierweg_status` | heating, cooling |

---

## SG Ready Signals

The heat pump supports SG Ready signals for smart grid integration. The `select.qube_sgready_mode` entity provides a user-friendly interface:

| Mode | SG Ready A | SG Ready B | Behavior |
|------|------------|------------|----------|
| **Off** | Off | Off | Normal operation |
| **Block** | On | Off | Block heat pump operation |
| **Plus** | Off | On | Regular heating curve, room +1K, DHW day mode |
| **Max** | On | On | Anti-legionella once, surplus curve, room +1K |

The underlying SG Ready A and B switches are hidden by default but remain available for advanced automations.

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
        entity_id: switch.qube_modbus_demand

  - alias: "Thermostat demand off"
    trigger:
      - platform: state
        entity_id: climate.your_thermostat
        attribute: hvac_action
        to: "idle"
    action:
      - service: switch.turn_off
        entity_id: switch.qube_modbus_demand
```

### 3. Control DHW Setpoint

Use the native number entity:

```yaml
service: number.set_value
target:
  entity_id: number.qube_tapw_timeprogram_dhwsetp_nolinq_setpoint
data:
  value: 52
```

---

## Multi-Device Configuration

All entity IDs include a configurable prefix (default: `qube`), ensuring consistent naming in both single and multi-device setups.

### Customizing the Entity ID Prefix

To customize the entity prefix for a heat pump:

1. Go to **Settings → Devices & Services → Integrations**
2. Find your Qube Heat Pump entry and click **Configure**
3. Change the **Entity ID prefix** (e.g., "basement", "main")
4. The integration will reload with the new prefix

### Example Entity IDs

| Heat Pump 1 (qube) | Heat Pump 2 (basement) |
|---------------------|------------------------|
| `sensor.qube_temp_outside` | `sensor.basement_temp_outside` |
| `switch.qube_modbus_demand` | `switch.basement_modbus_demand` |
| `sensor.qube_scop_day` | `sensor.basement_scop_day` |

---

## Use Cases

### Energy Monitoring Dashboard

Track your heat pump's energy efficiency over time:

```yaml
# Example energy dashboard card
type: statistics-graph
title: Monthly Energy & Performance
entities:
  - sensor.qube_electric_consumption_ch_month
  - sensor.qube_electric_consumption_dhw_month
  - sensor.qube_thermic_yield_month
stat_types:
  - sum
period:
  calendar:
    period: month
```

### Smart Grid Integration

Use SG Ready signals to optimize energy consumption based on electricity prices:

```yaml
automation:
  - alias: "Cheap electricity - boost heat pump"
    trigger:
      - platform: numeric_state
        entity_id: sensor.electricity_price
        below: 0.10
    action:
      - service: select.select_option
        target:
          entity_id: select.qube_sgready_mode
        data:
          option: "Plus"

  - alias: "Expensive electricity - reduce heat pump"
    trigger:
      - platform: numeric_state
        entity_id: sensor.electricity_price
        above: 0.30
    action:
      - service: select.select_option
        target:
          entity_id: select.qube_sgready_mode
        data:
          option: "Off"
```

### PV Surplus Heating

Combine with solar production to heat water when excess solar power is available:

```yaml
automation:
  - alias: "PV surplus - heat DHW"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_power
        above: 1500  # 1.5kW surplus
        for:
          minutes: 5
    condition:
      - condition: numeric_state
        entity_id: sensor.qube_temp_dhw
        below: 55
    action:
      - service: switch.turn_on
        entity_id: switch.qube_tapw_timeprogram_bms_forced

  - alias: "PV surplus ended - stop DHW boost"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_power
        below: 500
        for:
          minutes: 10
    action:
      - service: switch.turn_off
        entity_id: switch.qube_tapw_timeprogram_bms_forced
```

### Alarm Notifications

Get notified when the heat pump reports an alarm:

```yaml
automation:
  - alias: "Heat pump alarm notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.qube_glbal
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Heat Pump Alarm"
          message: "The Qube heat pump has reported an alarm. Check the status."
          data:
            priority: high
```

### Performance Tracking

Monitor SCOP (Seasonal Coefficient of Performance) trends:

```yaml
# Create a template sensor for SCOP status
template:
  - sensor:
      - name: "Heat Pump Efficiency Status"
        state: >
          {% set scop = states('sensor.qube_scop_month') | float(0) %}
          {% if scop >= 4.5 %}
            Excellent
          {% elif scop >= 3.5 %}
            Good
          {% elif scop >= 2.5 %}
            Fair
          {% else %}
            Poor
          {% endif %}
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

## Troubleshooting

### Common Issues

#### Cannot Connect to Heat Pump

**Symptoms**: Integration fails to load, entities show "unavailable"

**Solutions**:
1. **Verify network connectivity**
   ```bash
   ping <heat-pump-ip>
   ```
2. **Check Modbus port is open**
   ```bash
   nc -zv <heat-pump-ip> 502
   ```
3. **Verify heat pump has Modbus enabled** - Check heat pump controller settings
4. **Check firewall rules** - Ensure Home Assistant can reach port 502

#### Entities Show "Unknown" or "Unavailable"

**Symptoms**: Some or all entities show unknown/unavailable state

**Solutions**:
1. Check the `sensor.qube_metric_errors_read` for read error count
2. Enable debug logging to see detailed error messages:
   ```yaml
   logger:
     logs:
       custom_components.qube_heatpump: debug
   ```
3. Try reloading the integration (Settings → Devices & Services → Qube Heat Pump → Reload)

#### Energy Values Jump or Reset

**Symptoms**: Energy statistics show unexpected jumps or resets

**Explanation**: The heat pump occasionally reports glitched values. The integration uses monotonic clamping to filter these.

**Solutions**:
1. Check debug logs for "Monotonic clamp" messages
2. If values are genuinely wrong, use Home Assistant's statistics adjustment tool

#### Automations Not Triggering

**Symptoms**: Automations based on heat pump entities don't trigger

**Solutions**:
1. Verify entity IDs haven't changed (check Developer Tools → States)
2. Check entity state history to confirm state changes
3. For multi-device setups, ensure correct entity prefix

#### Slow Response to Commands

**Symptoms**: Switches/setpoints take time to reflect changes

**Explanation**: The 10-second polling interval means changes may take up to 10 seconds to appear.

**Solutions**:
1. Commands trigger an immediate refresh, so delays should be minimal
2. For critical timing, consider checking entity state before proceeding

### Debug Logging

Enable detailed logging for troubleshooting:

```yaml
logger:
  logs:
    custom_components.qube_heatpump: debug
    custom_components.qube_heatpump.hub: debug
    custom_components.qube_heatpump.coordinator: debug
```

### Getting Help

1. **Download diagnostics** - Settings → Devices & Services → Qube Heat Pump → Download diagnostics
2. **Check GitHub issues** - Search for similar issues at [GitHub Issues](https://github.com/MattieGit/qube_heatpump/issues)
3. **Open a new issue** - Include diagnostics file, debug logs, and problem description

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

---

## Notes

### DHW Setpoint Control

To control the DHW temperature setpoint, use the native number entity:

```yaml
service: number.set_value
target:
  entity_id: number.qube_tapw_timeprogram_dhwsetp_nolinq_setpoint
data:
  value: 52
```

### Entity ID Naming Convention

All entity IDs follow this pattern:
- Prefix: Configurable via Options (default: `qube`)
- Base: Vendor-defined key from the Modbus register (e.g., `temp_supply`, `bms_summerwinter`)

This aligns entity IDs with the vendor's Modbus documentation for easy cross-referencing.

### Terminology

- **CH** = Central Heating (formerly "CV" in Dutch)
- **DHW** = Domestic Hot Water (formerly "SWW" in Dutch)
