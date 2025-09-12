# Qube Heat Pump (Custom Integration)

This custom integration will read the Modbus registers of the Qube heatpump, creating sensors, binary sensors (alarms), and switches as defined in the Qube modbus documentation.

## Installation
- Via HACS: search for "Qube" (category: Integration), then download "Qube Heat Pump".
- Restart Home Assistant.

## Configuration
- Add via UI: Settings → Devices & Services → Integrations → "Add Integration" → "Qube Heat Pump".
- Enter the local IP (and optional port) of the heat pump.

## Notes
- Polling interval defaults to 10s.
- Float decoding assumes Big Endian word/byte order.
- Switch states are read from coils; writes use coil writes.
- The bundled `modbus.yaml` defines the sensors/binary_sensors/switches. The IP/host in that file is ignored at runtime and replaced by the value you enter in the config flow.
