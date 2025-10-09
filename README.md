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
- In some cases an update might result in duplicate entities for the Qube integration. In that case, you can go to the "Entities" overview in Home Assistant Settings. There you can filter on "Integration: qube" and "Status: unavailable". Tick the little selection box above the entities overview. After that you can batch delete those entities.

## Contributions
- Feel free to contribute to this repository.
- In case you'd like to share some support, feel free to [buy me a coffee](https://buymeacoffee.com/mattiegit).

**Diagnostics**
- Quick probe: run `modbus_probe.py` inside the Home Assistant container to verify raw Modbus values without the integration.
  - Example: `python3 /config/custom_components/qube_heatpump/modbus_probe.py --host 192.168.1.100 --unit 1 --address 32 --kind input --data-type float32`
  - If decoding looks off, try `--word-order little` and/or `--byte-order little` for 32‑bit values.
  - If a read fails, try `--address` one lower to check for 1‑based addressing in device docs.
  - If `pymodbus` is missing in the container Python, install temporarily for testing: `python3 -m pip install 'pymodbus>=3.9.0,<4'`.
 - Built‑in diagnostics: Settings → Integrations → Qube Heat Pump → Menu → Diagnostics exports a redacted snapshot (host, unit, entity counts) useful for troubleshooting.

**Multi‑hub behavior**
- Each heat pump is assigned a short label (`qube1`, `qube2`, …) which you can change in Options.
- Entity names can optionally include the label (see Options → “Show hub label in entity names”). They default to IDs without a label and the name is derived from the HR Energy modbus documentation.

**Error handling & recovery**
- The integration uses connection backoff and per‑read timeouts to avoid log flooding and to recover automatically when the device returns online.
- When the hub is unreachable, entities are marked unavailable by the coordinator until a successful update.
 
  
