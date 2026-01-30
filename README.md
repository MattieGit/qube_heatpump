# Qube Heat Pump (Custom Integration)

[![HACS Integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/mattiegit/qube_heatpump)](https://github.com/mattiegit/qube_heatpump/releases)

This Home Assistant integration connects to your Qube heat pump via Modbus/TCP and exposes the full set of registers as native entities (sensors, binary sensors, switches, numbers, buttons). It uses the [python-qube-heatpump](https://pypi.org/project/python-qube-heatpump/) library for standardized protocol-level entity definitions.

## Version 2.0.0 - Breaking Changes

**v2.0.0 is a breaking release** that restructures the integration to align with Home Assistant's official integration architecture. This prepares the path toward becoming an official HA core integration.

### What Changed

| Feature | v1.x | v2.0.0 |
|---------|------|--------|
| Entity definitions | YAML file (modbus.yaml) | Python library |
| Entity IDs | Mixed Dutch/English | Consistent English keys |
| DHW setpoint control | `qube_heatpump.write_register` service | `number.setpoint_dhw` entity |
| Multi-device support | Custom labels and options flow | Single device per entry |
| Coordinator pattern | Custom polling | `DataUpdateCoordinator` |

### Migration Guide

1. **Entity IDs will change** - Automations and dashboards referencing old entity IDs need updating
2. **Remove and re-add the integration** - A clean install is recommended
3. **Update dashboards** - See `examples/dashboard_qube_overview.yaml` for updated entity IDs
4. **Update automations** - Replace `qube_heatpump.write_register` calls with entity actions:
   ```yaml
   # Old (v1.x)
   service: qube_heatpump.write_register
   data:
     address: 173
     value: 52
     data_type: float32

   # New (v2.0.0)
   service: number.set_value
   target:
     entity_id: number.setpoint_dhw
   data:
     value: 52
   ```

### Key Entity ID Changes

| Old Entity ID | New Entity ID |
|---------------|---------------|
| `sensor.status_warmtepomp` | `sensor.status_heatpump` |
| `sensor.standby_verbruik` | `sensor.qube_standby_energy` |
| `sensor.elektrisch_verbruik_cv_maand` | `sensor.qube_energy_tariff_ch` |
| `sensor.elektrisch_verbruik_sww_maand` | `sensor.qube_energy_tariff_dhw` |

**Note:** "CV" has been renamed to "CH" (Central Heating) and "SWW" to "DHW" (Domestic Hot Water) for international clarity.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/mattiegit/qube_heatpump` as an **Integration**
4. Search for **Qube Heat Pump** and click **Download**
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/qube_heatpump` folder to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Integrations**
2. Click **Add Integration** and search for **Qube Heat Pump**
3. Enter the IP address or hostname of your heat pump
4. The integration auto-discovers all Modbus entities

## Features

### Entities

- **50+ sensors** - Temperatures, power, energy, setpoints, operating hours
- **37 binary sensors** - Alarms, valve states, digital inputs/outputs
- **7 switches** - Summer mode, DHW boost, SG Ready, heating curve
- **2 number entities** - DHW setpoint control
- **1 select entity** - SG Ready mode selector
- **1 button** - Integration reload

### Computed Sensors

Beyond raw Modbus values, the integration provides:

- **Standby power/energy** - Fixed 17W standby consumption tracking
- **Total energy (incl. standby)** - Combined active + standby consumption
- **Monthly energy splits** - CV and SWW consumption separated
- **SCOP calculations** - Daily and monthly efficiency ratios
- **Status sensors** - Human-readable heat pump and valve states

### Diagnostics

- **Qube Info sensor** - Version, host, entity counts
- **Error counters** - Connection and read error tracking
- **IP Address sensor** - Resolved IP for hostname setups

## Data Integrity

The integration implements **monotonic clamping** for `total_increasing` sensors. When the heat pump occasionally reports glitched values lower than the accumulated total (a known hardware quirk), the integration preserves the previous valid value to prevent energy statistics from being corrupted.

## Security Considerations

- **Network**: Modbus/TCP is an unencrypted protocol. The integration assumes a trusted local network
- **Write access**: The `write_register` service allows raw register writes for advanced users. Normal setpoint control should use the `number` entity actions
- **No external connections**: All communication stays within your local network

## Documentation

See the [project wiki](./wiki/README.md) for detailed documentation on:

- SG Ready signal configuration
- Virtual thermostat setup
- Dashboard examples
- Troubleshooting

## Contributions

Contributions are welcome! Please open issues for bugs or feature requests.

If you find this integration useful, consider [buying me a coffee](https://buymeacoffee.com/mattiegit).

## License

This project is licensed under the MIT License.
