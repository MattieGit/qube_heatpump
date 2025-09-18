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
## 2025.9.31 — 2025-09-16
- fix(yaml): update energy total sensors (addresses 69 and 71) to `state_class: total_increasing` with `device_class: energy` and `unit_of_measurement: kWh`.

## 2025.9.32 — 2025-09-16
- feat: Suggest entity_ids based on vendor unique_id (lowercased) with host+unit prefix via `suggested_object_id`; display names remain from YAML or translations.

## 2025.9.33 — 2025-09-16
- fix: Dataclass field order in `EntityDef` (place non-default fields before default). Resolves setup error on Python 3.13.

## 2025.9.34 — 2025-09-16
- feat: Actively align entity_id with vendor unique_id by updating the registry on first add (uses `<vendor_id>_<host>_<unit>`). Display names remain from YAML/translations.

## 2025.9.35 — 2025-09-16
- feat: Make host+unit prefix optional for entity_ids — try vendor-only first, fall back to `<vendor>_<host>_<unit>` only if there’s a conflict.

## 2025.9.36 — 2025-09-16
- fix: When `precision: 0`, return integer values (not floats) after rounding so kWh totals render without decimals in the UI.

## 2025.9.37 — 2025-09-16
- fix: Build entity unique_ids from vendor IDs without host+unit by default; add host+unit only when a conflict exists in the registry. Avoids unnecessary suffixes for single‑hub setups and reduces duplicate‑UID errors.

## 2025.9.38 — 2025-09-16
- fix: Suggest vendor-only entity_ids (no IP/unit) on first create; keep conflict fallback logic.
- feat: Set `suggested_display_precision` from YAML `precision` so kWh totals (precision 0) render without decimals.

## 2025.9.39 — 2025-09-16
- fix: Prevent duplicate unique_id collisions within a single hub by de-duplicating vendor IDs per platform during load (suffix with `<host>_<unit>` only when needed). This avoids the platform ignoring entities when two entries share the same vendor ID in YAML (e.g., addresses 44 and 46).

## 2025.9.40 — 2025-09-16
- feat: Adopt legacy suffixed unique_ids from the registry when present to avoid creating duplicates; prefer vendor-only otherwise.
- feat: Add a maintenance service `qube_heatpump.migrate_registry` with `dry_run` and `prefer_vendor_only` to rename entity_ids and update unique_ids where safe.

## 2025.9.43 — 2025-09-16
- fix(yaml): revert `GeneralMng_EletricPwr` (addr 61) to energy/kWh/total per validation.

## 2025.9.44 — 2025-09-16
- chore(yaml): set a distinct vendor unique_id for sensor at address 46 (`TapW_TimeProgram_DHWS_prog`) to avoid collisions with address 44.

## 2025.9.45 — 2025-09-16
- fix(yaml): set address 61 (`GeneralMng_EletricPwr`) to `device_class: power`, `unit_of_measurement: W`, and `state_class: measurement`; address 63 (`GeneralMng_TotalThermic_computed`) is already set to power/W/measurement.

## 2025.9.46 — 2025-09-16
- feat: Short hub labels (qube1/qube2/...) for multi‑hub setups; device names show the label.
- feat: Entity_id conflict fallback uses short label instead of IP/unit for readability.
- fix: Unique_id adoption checks that base UID belongs to this entry; otherwise prefers legacy UID to avoid cross‑entry collisions.

## 2025.9.47 — 2025-09-16
- feat: Add connection backoff and per‑read timeouts; throttle repeated read warnings per cycle.
- feat: Options Flow applies `unit_id` live; reload only when display mode changes.
- feat: Add diagnostics endpoint exporting redacted hub metadata and entity sample.
- docs: Document diagnostics, multi‑hub labels, naming behavior, and error handling.

## 2025.9.48 — 2025-09-16
- feat: Add Repairs flow for entity registry migration (invokes `migrate_registry`); create fixable issue when legacy suffixed unique_ids are detected.

## 2025.9.49 — 2025-09-16
- feat: Always include hub label in entity names and entity_ids; persist per‑entry label and allow editing in Options.
- feat: Migration service/Repairs flow supports enforcing label suffix on entity_ids.

## 2025.9.41 — 2025-09-16
- chore: Add `services.yaml` and service schema for `migrate_registry` to satisfy Hassfest validation.

## 2025.9.42 — 2025-09-16
- fix(yaml): update sensor at address 61 (`GeneralMng_EletricPwr`) to `device_class: power`, `unit_of_measurement: W`, and `state_class: measurement`.

## 2025.9.43 — 2025-09-16
- fix(yaml): revert `GeneralMng_EletricPwr` (addr 61) to energy semantics: `device_class: energy`, `unit_of_measurement: kWh`, `state_class: total` per user validation.
