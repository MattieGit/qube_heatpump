# WP Qube Heatpump (Custom Integration)

This custom integration reads Modbus TCP registers of a Qube heat pump, creating sensors, binary sensors (alarms), and switches defined in `conf_modbus.yaml`.

## Installation
- Via HACS: add this repo as a custom repository (category: Integration), then install "WP Qube Heatpump".
- Restart Home Assistant.

## Configuration
- Add via UI: Settings → Devices & Services → Integrations → "Add Integration" → "WP Qube Heatpump".
- Enter the local IP (and optional port) of the heat pump.
- The integration overrides the `host` value from `conf_modbus.yaml` with your IP.

## Notes
- Polling interval defaults to 10s.
- Float decoding assumes Big Endian word/byte order.
- Switch states are read from coils; writes use coil writes.

