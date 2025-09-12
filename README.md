# WP Qube Heatpump (Home Assistant)

This custom integration integrates the Qube heat pump (sold by HR‑Energy) into Home Assistant via Modbus/TCP. It creates sensors, binary sensors (alarms), and switches as defined in the bundled Modbus specification.

Notes:
- The Home Assistant Modbus integration is required and is listed as a dependency.
- You configure only the IP (and optional port) in the UI; default port is `502`.
- The bundled `modbus.yaml` defines entities; its `host` value is ignored at runtime and replaced by your configured IP.

## Install via HACS (recommended)
1) Ensure HACS is installed in your Home Assistant.
2) Go to `HACS → Integrations`.
3) If not installed yet: open the three‑dot menu → `Custom repositories`, add this repository URL as category `Integration`, then search for and install "WP Qube Heatpump".
4) Restart Home Assistant if prompted.
5) Add the integration via `Settings → Devices & Services → Add Integration → WP Qube Heatpump`.

## Manual install
1) Copy the `custom_components/qube_heatpump/` folder to `<config>/custom_components/qube_heatpump/`.
2) Restart Home Assistant.
3) Add the integration from the UI as above.

## Configuration
- During setup, enter the local IP of your Qube heat pump (visible on the device display). Use port `502` unless you know you changed it.
- The integration will set up sensors, binary sensors (alarms), and switches automatically.

## SG Ready & Automations
- Switches enable SG Ready behavior and allow automations like triggering the anti‑legionella program (e.g., when surplus solar is available).

## Duplicate entities
If you already have a Modbus integration configured for your Qube heat pump, this integration may create duplicates. Remove the old/unavailable entities manually (filter by name and status "Unavailable").

## Support / Issues
This is an initial version; please report issues via GitHub Issues. Thanks!
