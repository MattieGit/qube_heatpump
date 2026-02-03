# Qube Heat Pump (Custom Integration)

[![HACS Integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/mattiegit/qube_heatpump)](https://github.com/mattiegit/qube_heatpump/releases)

This Home Assistant integration connects to your Qube heat pump via Modbus/TCP and exposes the full set of registers as native entities (sensors, binary sensors, switches, numbers, buttons). It uses the [python-qube-heatpump](https://pypi.org/project/python-qube-heatpump/) library for standardized protocol-level entity definitions.

## Entity Naming

All entity IDs include a configurable prefix (default: `qube`) for clear identification:

```
sensor.qube_temp_supply
sensor.qube_temp_return
sensor.qube_energy_total_electric
switch.qube_bms_summerwinter
select.qube_sgready_mode
```

The prefix can be customized via the integration's Options (Configure button) to match your device name.

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

- **Sensors** - Temperatures, power, energy, setpoints, operating hours
- **Binary sensors** - Alarms, valve states, digital inputs/outputs
- **Switches** - Summer mode, DHW boost, SG Ready, heating curve
- **Number entities** - DHW setpoint control
- **Select entity** - SG Ready mode selector
- **Button** - Integration reload

### Computed Sensors

Beyond raw Modbus values, the integration provides:

- **Standby power/energy** - Fixed 17W standby consumption tracking
- **Total energy (incl. standby)** - Combined active + standby consumption
- **Monthly/daily energy splits** - CH and DHW consumption separated
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
