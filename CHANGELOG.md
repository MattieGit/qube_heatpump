# Changelog

All notable changes to this project are documented in this file. This project uses semantic-style versioning aligned to the year.month.patch used by Home Assistant custom components.

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
