# Qube Heat Pump (Custom Integration)

[![HACS Integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/mattiegit/qube_heatpump)](https://github.com/mattiegit/qube_heatpump/releases)

This Home Assistant integration connects to your Qube heat pump (HR-energy) over Modbus/TCP and exposes its registers as native entities: sensors, binary sensors, switches, numbers, a select, buttons, a water heater and an optional thermostat. It uses the [python-qube-heatpump](https://pypi.org/project/python-qube-heatpump/) library, the same library as the official core integration.

## Which integration should I use?

Home Assistant also ships an official [Qube heat pump integration](https://www.home-assistant.io/integrations/hr_energy_qube/) (`hr_energy_qube`). The same author maintains both, and both are maintained for the long term. Use one of them per heat pump.

- **Most new users: the core integration** (Home Assistant 2026.11 or later). It covers monitoring, the energy dashboard and the everyday controls: summer mode, heating demand, the heating curve, SG Ready and hot water through the water heater. It needs no HACS, it is reviewed by Home Assistant and updates with Home Assistant, it is rated platinum on the integration quality scale, and its entity names are translated into your Home Assistant language.
- **This custom integration** if you need any of:
  - Home Assistant as the room thermostat instead of a LinQ (virtual thermostat)
  - A daily hot-water schedule without writing automations
  - Daily and monthly energy split into heating and hot water, standby consumption and SCOP
  - Heating and cooling setpoints without the heating curve (`number` entities)
  - The full register set (operating hours, all DHW setpoints, valve status) and the `write_register` action
  - New features first: they are tried here before they move to core
- **Already using this integration?** Keep it if you use any of the above. If you only use entities that core also has, you can switch: [Switching to the core integration](./wiki/README.md#switching-to-the-core-integration) keeps your history.

The wiki has a [side-by-side comparison](./wiki/README.md#which-integration-should-i-use).

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/mattiegit/qube_heatpump` as an **Integration**
4. Search for **Qube heat pump** and click **Download**
5. Restart Home Assistant

Requires Home Assistant 2025.3 or later.

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/qube_heatpump` folder to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

On the same network as Home Assistant the heat pump is discovered automatically: select **Add** on the discovered Qube heat pump under **Settings → Devices & services** and choose a device name. To add it manually:

1. Go to **Settings → Devices & services → Integrations**
2. Click **Add Integration** and search for **Qube heat pump**
3. Enter the IP address or hostname of your heat pump and a device name. `qube.local` works when Home Assistant and the heat pump are on the same network; in a separate VLAN, use the IP address
4. The integration creates all Modbus entities

The optional virtual thermostat and DHW schedule are enabled in the **Configure** dialog of the entry.

From Home Assistant 2026.11 the core integration discovers the heat pump as well. If you use this integration, select **Ignore** on that second discovered card.

## Features

### Entities

- **Sensors** - Temperatures, power, energy, setpoints, operating hours
- **Binary sensors** - Alarms, valve states, digital inputs/outputs
- **Switches** - Summer mode, DHW boost, anti-legionella, heating curve, heat demand, DHW schedule
- **Number entities** - DHW setpoint (Modbus, register 173), heating setpoint without curve (register 101), cooling setpoint without curve (register 103)
- **Select entity** - SG Ready mode selector
- **Water heater** - Domestic hot water: DHW temperature, setpoint and the forced DHW run in one entity
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
- **Download diagnostics** - Entry data and options (host/IP redacted), the heat pump's mDNS announcement, the values as read and as shown in Home Assistant, and the energy counter cache
- **Software version** - Read from the heat pump's mDNS announcement (the version on the display). It shows as *unknown* when the heat pump is in another VLAN; see [Network & mDNS](./wiki/README.md#network--mdns)

### Data integrity

The heat pump occasionally reports an energy total slightly lower than before. The integration holds the previous value so the energy statistics are not corrupted, and accepts a drop of more than 1 kWh that lasts three polls as a genuine counter reset. See [Data Integrity](./wiki/README.md#data-integrity--monotonic-clamping).

## Entity IDs

Entity IDs are `<platform>.<device name>_<key>`, for example `sensor.qube_1_temp_supply` with the default device name "qube 1". The key is the vendor's Modbus register key, so the IDs do not depend on your Home Assistant language and can be looked up in the Modbus documentation. See [Entity Reference](./wiki/README.md#entity-reference).

## Security

Modbus/TCP is unencrypted and has no authentication, so keep the heat pump on a trusted local network. The integration only talks to the heat pump; nothing leaves your network. The `write_register` action only writes the registers and coils the integration knows as writable. See [Security Considerations](./wiki/README.md#security-considerations).

## Removing the Integration

Delete the entry via **Settings → Devices & services → Qube heat pump → ⋮ → Delete**. Home Assistant removes the device and its entities, and the integration removes its alarm group and energy counter cache. See the [wiki](./wiki/README.md#removing-the-integration).

## Documentation

The [project wiki](./wiki/README.md) covers:

- Choosing between this and the core integration, and switching
- Supported firmware, network and mDNS
- Entity reference and computed sensors
- Hot water control, SG Ready, the virtual thermostat and the DHW schedule
- Automation and dashboard examples
- Troubleshooting and diagnostics

## Contributions

Contributions are welcome! Please open issues for bugs or feature requests.

If you find this integration useful, consider [buying me a coffee](https://buymeacoffee.com/mattiegit).

## License

This project is licensed under the GNU General Public License v3.0; see [LICENSE](LICENSE).
