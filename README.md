# Qube Heat Pump (Custom Integration)

This integration connects Home Assistant to the Qube heat pump over Modbus/TCP and exposes the full set of registers as native sensors, binary sensors, switches, buttons, and diagnostics. It keeps naming aligned with the vendor documentation while adding value-add entities (standby power, CV/SWW energy splits, diagnostics metrics, etc.) so you can monitor and automate the system with minimal manual setup.

## Installation
1. Open HACS → Integrations and search for **Qube Heat Pump** (category: Integration).
2. Click *Download*, wait for HACS to finish, then restart Home Assistant.

## Configuration
1. Go to *Settings → Devices & Services → Integrations*.
2. Click **Add Integration** and select **Qube Heat Pump**.
3. Enter the IP/hostname of the heat pump. If you are using multiple heat pumps, please always enter an IP address.
4. The integration auto-discovers all Modbus entities and creates diagnostics sensors; multi-hub setups are handled automatically.
5. Use the integration *Options* to rename the hub label or toggle label suffixes on entity IDs. Full behavioural details live in the [project wiki](./wiki/README.md).

## Contributions
- Feel free to contribute to this repository.
- In case you'd like to share some support, feel free to [buy me a coffee](https://buymeacoffee.com/mattiegit).
  
