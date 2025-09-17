# Changelog

All notable changes to this project are documented in this file. This project uses semantic-style versioning aligned to the year.month.patch used by Home Assistant custom components.

## 2025.9.30 — 2025-09-16
- feat: Keep friendly YAML names for display by default; base unique_ids on vendor IDs (lowercased) and namespace with `<host>_<unit>` for multi‑hub.
- feat(options): Add toggle "Use vendor names for display"; reloading entry applies display mode.
- feat(i18n): Add entity name translations (en/nl) resolved by vendor ID; defaults to English.
- fix: Automatically lowercase vendor `unique_id` values from YAML on load (no manual edits required).

## 2025.9.29 — 2025-09-16
- feat: Add per-entity `min_value` clamp in hub; configured `Gemeten Flow` with `min_value: 0` to report 0 instead of slight negative values when idle.

## 2025.9.28 — 2025-09-16
- fix: Avoid sensor collisions across multiple hubs by namespacing YAML-defined sensor unique_ids with `<host>_<unit>`.
  - Note: sensors may re-register with new unique_ids; clean up old registry entries if duplicates appear.

## 2025.9.27 — 2025-09-16
- revert: Remove vendor/original name attribute exposure and extra metadata on entities, restoring the prior entity model.

## 2025.9.26 — 2025-09-16
- feat: Preserve vendor/original names alongside friendly names; expose `vendor_name` and addressing metadata as entity attributes for sensors, binary_sensors and switches.

## 2025.9.25 — 2025-09-16
- fix: Support multiple hubs/devices in parallel by including host+unit in entity unique_ids and device identifiers to prevent collisions.
  - Note: existing entities may re-register with new unique_ids; if duplicates appear in the registry, remove the older entries once verified.

## 2025.9.24 — 2025-09-16
- feat: Add computed/template sensors (status, driewegklep DHW/CV, vierwegklep heat/cool) with automatic source detection independent of entity_id suffixes.
- docs/chore: Relocate `modbus_probe.py` into integration directory and update README usage.
- fix: Ensure Options/Configure is visible by exposing options flow in `__init__`.

## 2025.9.23 — 2025-09-16
- feat: Expose Options Flow in `__init__` so Configure/Options appears in UI.
- chore: Move `modbus_probe.py` into integration directory for visibility.
- docs: Update README with probe usage and tips.

## 2025.9.22 — 2025-09-16
- feat: Add Options Flow to set Modbus Unit/Slave ID with restart-less apply; includes translations and live coordinator refresh.

## 2025.9.21 — 2025-09-16
- fix: Align hub Modbus calls with the probe script by trying `slave` then `unit` kwargs (and fallback) for maximum pymodbus 3.x compatibility.

## 2025.9.20 — 2025-09-16
- chore: Add `scripts/modbus_probe.py` to test Modbus/TCP reads from the HA terminal (helps diagnose addressing/endianness and connectivity).

## 2025.9.19 — 2025-09-15
- fix: Support both `slave` and `unit` kwargs across `pymodbus` versions via runtime signature detection.
- fix: Improve connection checks and error logging for easier diagnostics.
- feat: Add 1-based addressing fallback (retry `address-1`) when a register read fails.

## 2025.9.18 — 2025-09-15
- fix: Restore working config flow by relaxing dependency to `pymodbus>=3.9.0,<4` (compatible with Python 3.13) so HA can install requirements during flow.

## 2025.9.17 — 2025-09-15
- fix: Correct pymodbus calls to use `slave=` kwarg for reads/writes; add `isError()` checks and logging to diagnose read failures.
- chore: Restore `pymodbus==3.6.6` manifest requirement to ensure dependency availability in HA.

## 2025.9.16 — 2025-09-15
- fix: Sensors no longer show Unknown by passing correct Modbus `unit_id` on all reads/writes (default 1; configurable via YAML).
- refactor: Strip leading "WP-Qube"/"WP Qube" prefix from entity names for clarity.

## 2025.9.15 — 2025-09-15
- fix: Resolve setup error by avoiding `pymodbus.payload` import and manually decoding Modbus registers (big‑endian). Prevents `ModuleNotFoundError` on certain pymodbus versions.

## 2025.9.14 — 2025-09-14
- chore: Bump version to calendar date for config flow simplification and connectivity validation.

## 2025.9.3 — 2025-09-12
- fix: Address config flow error by lazy‑importing the hub in `__init__.py` so the flow loads before optional deps are installed.
- chore: Add `pymodbus==3.6.6` to `manifest.json` requirements.

## 2025.9.2 — 2025-09-12
- updated domain from wp_qube to qube_heatpump to align with Home Assistant brand

## 2025.9.1 — 2025-09-10
- feat: Load entities from `modbus.yaml` and override host/port from the config flow (no hardcoded IP).
- fix: Align integration domain to `wp_qube` to match directory and code constant.
- chore: Declare `config_flow: true` in `manifest.json`.
- docs: Add HACS installation instructions to `README.md` and note about YAML host override.
- docs: Add GitHub release template at `.github/release_template.md`.
- chore: Enable HACS README rendering via `hacs.json`.
- chore: Bump version to `2025.9.1`.

## 2025.9.0 — 2025-09-09
- feat: Initial public version of the WP Qube Heatpump integration.
- feat: Basic Modbus/TCP hub, sensors, binary_sensors, and switches.
- docs: Initial documentation.
