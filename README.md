# Qube Heat Pump (Custom Integration)

[![HACS Integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/mattiegit/qube_heatpump)](https://github.com/mattiegit/qube_heatpump/releases)

This Home Assistant integration connects to your Qube heat pump via Modbus/TCP and exposes the full set of registers as native entities (sensors, binary sensors, switches, numbers, select, buttons). It uses the [python-qube-heatpump](https://pypi.org/project/python-qube-heatpump/) library for standardized protocol-level entity definitions.

## Entity Naming

Entity IDs are `<platform>.<device name>_<key>`. The device name you enter during setup is slugified and used as prefix; the default name "qube 1" gives:

```
sensor.qube_1_temp_supply
sensor.qube_1_temp_return
sensor.qube_1_energy_total_electric
switch.qube_1_bms_summerwinter
select.qube_1_sg_ready_mode
```

The key is the vendor's Modbus register key, so an entity ID can be looked up directly in the Modbus documentation. The device name can be changed later via the integration's **Configure** dialog; this renames all entity IDs. In the wiki and examples, `qube` stands for your slugified device name.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/mattiegit/qube_heatpump` as an **Integration**
4. Search for **Qube heat pump** and click **Download**
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/qube_heatpump` folder to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Integrations**
2. Click **Add Integration** and search for **Qube heat pump**
3. Enter the IP address or hostname of your heat pump and a device name
4. The integration creates all Modbus entities

The optional virtual thermostat and DHW schedule are enabled in the **Configure** dialog of the entry.

## Features

### Entities

- **Sensors** - Temperatures, power, energy, setpoints, operating hours
- **Binary sensors** - Alarms, valve states, digital inputs/outputs
- **Switches** - Summer mode, DHW boost, anti-legionella, heating curve, heat demand, DHW schedule
- **Number entities** - DHW setpoint (Modbus, register 173), heating setpoint without curve (register 101), cooling setpoint without curve (register 103)
- **Select entity** - SG Ready mode selector
- **Buttons** - Integration reload, clear energy counter cache
- **Climate** - Optional virtual thermostat driven by an external temperature sensor

### Computed Sensors

Beyond raw Modbus values, the integration provides:

- **Standby power/energy** - Fixed 17W standby consumption tracking (the heat pump's own power and energy registers exclude standby)
- **Total energy (incl. standby)** - Combined active + standby consumption
- **Monthly/daily energy splits** - CH and DHW consumption separated
- **SCOP calculations** - Daily and monthly efficiency ratios
- **Status sensors** - Human-readable heat pump and valve states

### Diagnostics

- **Info sensor** - Firmware and integration version, host, label, error counters as attributes
- **Error counters** - Connection and read error tracking
- **IP address sensor** - Resolved IP for hostname setups
- **Energy totals not advancing** - Problem binary sensor raised when the energy totalisers stop advancing while the heat pump draws power
- **Download diagnostics** - Entry data and options (host/IP redacted), firmware version, hub info, entity list and the current register data

## Is my DHW schedule active?

Two diagnostic entities on the device page reflect the DHW schedule configured in the integration options: `binary_sensor.<label>_dhw_schedule` is **on** while the schedule option is enabled and lists the start and end time, the setpoint source (controller Modbus setpoint or a fixed value), whether the daily window is currently active and when it last started and ended; `sensor.<label>_dhw_schedule_next_start` shows the next scheduled start as a timestamp and is *unknown* while the schedule is off. At startup the log also states `DHW schedule enabled 13:00-15:00, setpoint source: controller Modbus setpoint` or `DHW schedule disabled`.

## Data Integrity

The integration implements **monotonic clamping** for `total_increasing` sensors. When the heat pump occasionally reports glitched values lower than the accumulated total (a known hardware quirk), the integration preserves the previous valid value to prevent energy statistics from being corrupted. A drop of more than 1 kWh that persists for three consecutive polls is treated as a genuine counter reset and accepted as the new baseline (logged as a warning). The cache can be cleared manually with the "Clear energy counter cache" button.

## Security Considerations

- **Network**: Modbus/TCP is an unencrypted protocol. The integration assumes a trusted local network
- **Write access**: The `write_register` service allows raw register writes for advanced users. Normal setpoint control should use the `number` entity actions
- **No external connections**: All communication stays within your local network

## Removing the Integration

Delete the entry via **Settings → Devices & Services → Qube heat pump → ⋮ → Delete**. Home Assistant removes the device and its entities, the `group.qube_alarms_<device name>` helper group is removed when the entry unloads, and the monotonic-clamping cache file `.storage/qube_heatpump_monotonic_<entry_id>` is deleted with the entry. Nothing is left behind. See the [wiki](./wiki/README.md#removing-the-integration) for details.

## Documentation

See the [project wiki](./wiki/README.md) for detailed documentation on:

- Entity reference and computed sensors
- SG Ready signal configuration
- Virtual thermostat setup and DHW schedule
- Dashboard examples
- Troubleshooting and diagnostics

## Contributions

Contributions are welcome! Please open issues for bugs or feature requests.

If you find this integration useful, consider [buying me a coffee](https://buymeacoffee.com/mattiegit).

## License

This project is licensed under the GNU General Public License v3.0; see [LICENSE](LICENSE).
