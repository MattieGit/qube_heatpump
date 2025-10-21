# Qube Heat Pump Wiki

## Table of Contents
1. [Computed & Derived Entities](#computed--derived-entities)
2. [Diagnostics Toolkit](#diagnostics-toolkit)
3. [Multi-Hub Behaviour](#multi-hub-behaviour)
4. [Error Handling & Recovery](#error-handling--recovery)

---

## Computed & Derived Entities

Beyond the raw Modbus registers, the integration exposes several helper entities that make day-to-day monitoring easier:

### Diagnostic Sensors
- **Qube info** – summarises firmware version, hub label, host/IP, and total entity counts.
- **Qube connect/read errors** – incrementing counters that help identify Modbus stability issues.
- **Qube sensor/binary sensor/switch count** – live totals so you can confirm everything is still registered for the hub.
- **Qube IP address** – resolved IP in case the device is addressed by hostname.

### Energy & Power
- **Standby vermogen** – fixed 17 W standby power reported as a sensor.
- **Standby verbruik** – integrates standby power over time (kWh) so long recordings include the “idle” cost.
- **Totaal elektrisch verbruik (incl. standby)** – combines the vendor’s total power counter with the standby integration above.
- **Elektrisch verbruik CV (maand)** – accumulates the heat pump’s electrical usage while the three-way valve is in CV mode.
- **Elektrisch verbruik SWW (maand)** – accumulates usage while the valve is in domestic hot water (SWW) mode.
- **Tarief elektrisch verbruik (select)** – optional manual override letting you pin the tariff to `CV` or `SWW` when automations aren’t available.

### Status Helpers
- **Status warmtepomp** – decodes the unit-status register to a human-readable state (Heating, Cooling, Standby, etc.).
- **Qube Driewegklep DHW/CV status** – tracks whether the three-way valve is in DHW or CV mode.
- **Qube Vierwegklep verwarmen/koelen status** – reports whether the four-way valve is set for heating or cooling.

## Diagnostics Toolkit

Two tooling layers are available when something seems off:

### Built-in Home Assistant diagnostics
1. Go to *Settings → Devices & Services → Qube Heat Pump → ⋮ Menu → Diagnostics*.
2. Download the snapshot – it includes hub metadata, resolved IP, error counters, and entity totals.
3. Attach the file when raising issues so we can compare against known-good states.

### `modbus_probe.py`
- Located under `custom_components/qube_heatpump/`.
- Run inside the Home Assistant container for one-off register checks:
  ```bash
  python3 /config/custom_components/qube_heatpump/modbus_probe.py \
      --host 192.168.1.100 --unit 1 --address 32 --kind input --data-type float32
  ```
- Use `--word-order` / `--byte-order` to test alternative endianness and `--address` to probe off-by-one mappings.

## Multi-Hub Behaviour

- Each hub receives a persistent label (`qube1`, `qube2`, …) that you can rename under *Options*.
- Entity IDs keep their vendor-aligned slugs for a single hub. As soon as multiple hubs are installed the integration automatically appends the label (e.g. `_qube2`) so there are no collisions.
- Diagnostics entities always carry the label in both single- and multi-hub scenarios to make troubleshooting easier.
- The Options toggle **Add hub label to entity IDs** mirrors the automatic behaviour; when you enable it, labels remain appended even in single-hub environments.

## Error Handling & Recovery

- The integration uses exponential backoff on connection failures so the logs remain readable and the device isn’t hammered while offline.
- Every read has a short timeout; on failure we increment the diagnostic counters and try again next cycle.
- Entities are surfaced through Home Assistant’s `DataUpdateCoordinator`. If the pump is offline, entities report `unavailable` until Modbus connectivity returns.
- When you operate multiple hubs, the coordinator for each hub runs independently: an outage on one pump does not block updates for the others.
