# Changelog

All notable changes to this project are documented in this file. This project uses semantic-style versioning aligned to the year.month.patch used by Home Assistant custom components.

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
