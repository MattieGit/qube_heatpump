# Repository Guidelines

## Project Structure & Module Organization
- Root contains JSON file for HACS integration for Home Assistant with name "qube_heatpump".
- Documentation for publishing a HACS integration can be found via this link: https://www.hacs.xyz/docs/publish/integration/
- Keep the manifest `documentation` URL pointing at the project wiki (https://github.com/MattieGit/qube_heatpump/wiki) so HA and HACS surface it.
- custom_components/ contains the files for the HACS integration
- Place reusable code in `src/` (e.g., parsers, validators); command-line helpers in `scripts/`.
- Add tests in `tests/` mirroring `src/` structure (e.g., `tests/test_validate_config.py`).
- Keep sample fixtures in `tests/fixtures/` and any non-code assets in `assets/`.

## Build, Test, and Development Commands
- Lint YAML: `yamllint conf_modbus.yaml` (ensure two-space indentation, no tabs).
- Run linters/hooks (if configured): `pre-commit run --all-files`.
- Python tests (when present): `pytest -q` from repo root.
- Validate config (example): `python scripts/validate_config.py conf_modbus.yaml` to check schema and references.
- **HACS validation (local)**: Always run before pushing to GitHub:
  ```bash
  TOKEN=$(gh auth token) && docker run --rm --platform linux/amd64 \
    -v "$(pwd):/github/workspace" \
    -e "INPUT_GITHUB_TOKEN=${TOKEN}" \
    -e "GITHUB_TOKEN=${TOKEN}" \
    -e "GITHUB_REPOSITORY=MattieGit/qube_heatpump" \
    -e "INPUT_CATEGORY=integration" \
    ghcr.io/hacs/action:main
  ```
  Note: Requires Docker running. On Apple Silicon (arm64), the `--platform linux/amd64` flag is required as the HACS action image only exists for amd64.
- Current configuration has been fully validated and is working as expected. Don't make any breaking changes.

## Coding Style & Naming Conventions
- YAML: two-space indent, lowercase keys in `snake_case`, comments with `#` above the field they describe.
- File names: use `.yaml` (not `.yml`); environment-specific overrides as `conf_modbus.<env>.yaml` (e.g., `conf_modbus.dev.yaml`).
- Python (if added): PEP 8, 88–100 char lines, type hints required in `src/`.

## Testing Guidelines
- Prefer `pytest`; name tests `test_*.py` and functions `test_*`.
- Add schema-based tests (e.g., using `jsonschema`/`pykwalify`).
- Include representative fixtures under `tests/fixtures/` and validate both happy-path and edge cases.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`.
- Keep commits scoped and descriptive; include rationale for config changes and potential impact on downstream systems.
- PRs should include: summary, linked issues, screenshots/log snippets when relevant, and validation steps (lint + tests + config validation).

## Security & Configuration Tips
- Do not commit secrets; reference them via `${ENV_VAR}` and provide a `.env.example`.
- Validate IPs, ports, and device IDs; prefer named constants and comments for non-obvious values.
- If adding code that reads the config, fail fast with clear error messages and schema validation.

## Agent-Specific Instructions
- Keep edits minimal and focused; avoid renaming or moving files unless necessary.
- Obey this guide’s structure for any new files; validate YAML before opening a PR.
- Use SSH for Git operations (remote: `git@github.com:MattieGit/qube_heatpump.git`) instead of HTTPS when pushing.
- When adding or changing any user-facing names (entities, sensors, switches, buttons, diagnostics), update the translations in `custom_components/qube_heatpump/translations/` (both `entity_names.en.json` and `entity_names.nl.json`) to keep the UI consistent.

---

# Qube Heatpump Integration — Working Notes

This repository contains a HACS custom integration for Home Assistant that integrates the Qube heat pump via Modbus/TCP using `pymodbus`.

## Scope & Goals
- Support single and multi-device (multiple heat pumps) setups cleanly.
- Improve entity naming and unique_id stability, especially across multiple hubs.
- Provide richer Diagnostics: attributes and dedicated metric sensors.
- Show useful details in Device info (e.g., `sw_version`).
- Keep releases versioned and published as GitHub pre-releases.

## Key Changes Implemented
- Unique IDs and naming
  - Prefer vendor-provided unique IDs from YAML (`unique_id`) where available.
  - When multiple hubs exist, append a hub label (e.g., `qube1`, displayed as “qube 1”) to avoid collisions.
  - Auto-migrate legacy host/unit-suffixed unique_ids to label-suffixed ones for known entity families (computed/info/reload/sensors).
- Entity IDs prefer “vendor_id + label” where possible; conflicts are avoided if an entity_id already exists.
- During setup the integration removes any existing registry entries for the config entry and re-registers them via `entity_registry.async_get_or_create` with vendor-based slugs so legacy friendly-name slugs never persist.

- Diagnostics
  - Diagnostic “Qube info” sensor: keeps attributes like version, label, host, unit, error counters, and entity counts.
  - Dedicated metric sensors added so users can mark them as Preferred on the device page:
    - `Qube connect errors`, `Qube read errors`, `Qube sensor count`, `Qube binary sensor count`, `Qube switch count`.
  - When more than one device is configured, Diagnostics friendly names automatically include the hub label suffix. Unique_ids for Diagnostics are label-suffixed in multi-device setups.

- Device Info
  - `sw_version` is populated from `manifest.json` where supported (present on Sensors and Buttons; extend to other platforms if needed).

- Modbus spec cleanups
  - Removed invalid input register 63 from `modbus.yaml` per vendor guidance.
  - On setup, the integration purges the now-obsolete entity from the registry by known unique_ids.

- Options Flow
  - Added an option `show_label_in_name` (“Show hub label in entity names”).
  - Effective only when multiple heat pumps exist; single-device setups keep names unchanged.
  - Config and options forms should include a short link to the wiki for additional guidance.

## Release & Versioning
- Workflow: `.github/workflows/release.yml` creates GitHub Releases on tags matching `20YY.M.N` and marks them as pre-releases.
- Manifest version is kept in `custom_components/qube_heatpump/manifest.json`.
- Recent pre-release tags (summary):
  - 2025.9.77 — Migrate unique_ids to label-based scheme; version bump.
  - 2025.9.78 — Add `sw_version` to Device info across entities (in progress where applicable).
  - 2025.9.79 — Add dedicated diagnostic metric sensors.
  - 2025.9.80 — Remove input register 63 from `modbus.yaml`; registry cleanup on setup.
  - 2025.9.81 — Append hub label in Diagnostics friendly names when multiple devices exist.
  - 2025.9.82 — Migrate Diagnostics unique_ids to include label suffix for multi-device setups.
  - 2025.9.83 — Options Flow toggle: “Show hub label in entity names”; effective only when multiple devices exist.

## Files of Interest
- `custom_components/qube_heatpump/__init__.py`
  - Loads Modbus YAML spec; builds entities; coordinates data updates.
  - Unique_id migration (legacy host/unit suffix → label suffix) and registry housekeeping.
  - Cleanup for deprecated sensor (input register 63) by unique_id.
  - Tracks multi-device state and exposes flags used by platforms:
    - `apply_label_in_name`, `multi_device`.

- `custom_components/qube_heatpump/config_flow.py`
  - Config flow for creating entries; connectivity check on setup.
  - Options Flow exposes `show_label_in_name` toggle (effective in multi-device setups).

- Platforms
  - `sensor.py`
    - `QubeInfoSensor` with diagnostics attributes and `sw_version` in Device info.
    - `QubeMetricSensor` (5 dedicated diagnostic metrics; label-suffixed in multi-device setups).
    - `WPQubeSensor` and `WPQubeComputedSensor` adopt vendor IDs and label-based naming.
  - `binary_sensor.py`, `switch.py`, `button.py`
    - Label-aware names; prefer vendor_id + label suggested object_ids.
    - `button.py` includes `QubeReloadButton` and sets `sw_version` in Device info.
    - TODO: align `binary_sensor.py` and `switch.py` Device info with `sw_version` for consistency.

- Modbus spec
  - `custom_components/qube_heatpump/modbus.yaml` — canonical register map bundled with the integration.
  - `template_sensors.yaml` retained for reference; equivalent computed sensors are implemented in code.

- Translations
  - `custom_components/qube_heatpump/translations/*.json` — includes `entity_names.*.json` for vendor-ID based display names, and `en.json` for basic flow text.

## Naming & Unique ID Patterns
- Hub label: auto-assigned `qubeN` (persisted in options) when first configured; displayed as “qube N”.
- Unique_id patterns (examples):
  - Diagnostics: `qube_info_sensor_<label>`, `qube_metric_<kind>_<label>`.
  - Reload button: `qube_reload_<label>`.
  - Computed: `wp_qube_<suffix>_<label>`.
  - Raw sensors (fallback): `wp_qube_sensor_<label>_<type>_<addr>`.
- Entity IDs prefer `vendor_id + label` when a vendor `unique_id` is present, with conflict checks to avoid clobbering existing IDs.

## Multi-Device Behavior
- Diagnostics: always append label suffix to friendly names when more than one heat pump exists; unique_ids for Diagnostics also adopt label suffix in that case.
- Sensors/Switches: label suffix in friendly names only when the Options toggle is on AND multiple devices exist.

## How To Cut a New Pre-Release
- Bump `version` in `manifest.json` (e.g., `2025.9.84`).
- Create a tag that matches the workflow pattern (e.g., `git tag 2025.9.84 && git push origin --tags`).
- GitHub Actions workflow will publish a pre-release automatically.
- Follow Conventional Commits in PRs/commits for clarity.
- Use Calendar Versioning based on the current date (e.g., Jan 4 2026 -> `2026.1.4`); tag and manifest version must remain in sync.

## Development Notes
- YAML style: two-space indent; lower_snake_case keys; comments above fields.
- Keep changes minimal and focused; avoid breaking existing entity_ids whenever possible. Unique_id migrations include conflict checks.
- Prefer vendor `unique_id` adoption when present in YAML; use label suffix for disambiguation only on collision.
- For Options Flow or naming changes, reload the config entry to apply name/entity_id updates.

## Open Follow-Ups / TODOs
- Ensure `sw_version` is present in Device info for `binary_sensor` and `switch` to match sensors/buttons.
- Add tests (pytest) for Options Flow behavior, unique_id migrations, and registry cleanup.
- Consider extending translations beyond English for the Options UI.
- Verify external documentation links (currently point to previous repo path in `manifest.json`).

## Recent Learnings (2025-10)
- **Options flow usability**: The Configure cog must offer a text input for the Modbus unit ID (default `1`) plus clear descriptions explaining vendor-name and label toggles. Multi-device state is derived automatically; label suffixes should only appear when the option is enabled or more than one hub exists.
- **Statistics cleanup**: Any recorder maintenance (e.g., clearing legacy stats for enum sensors) has to use `Recorder.async_clear_statistics` to stay on the recorder thread. Guard for recorder availability and do nothing if the component is absent.
- **Label-aware unique_ids**: Single-device setups should default to host/unit-based unique_ids, while multi-device or explicit label toggles enforce the label suffix. Diagnostics, computed sensors, and raw sensors all need to follow the same rule to avoid duplicate or orphaned entities.
- **Vendor naming option**: Suggested object_ids and recreated entity_ids should prefer the vendor `unique_id` from YAML so users can cross-reference vendor documentation. Only add label suffixes when multi-device behavior requires it.
- **Testing expectations**: After significant naming or registry changes, run `pytest -q`. Add dedicated tests (e.g., `tests/test_options_flow.py`) to capture regressions around option persistence and naming rules.
- **Offline migration tooling**: Prototype script `scripts/plan_registry_migration.py` (backed by helpers in `src/qube_migration/`) operates on an exported `core.entity_registry` to plan/vendor-align entity_ids and unique_ids. It defaults to dry-run mode, emits conflict/unmatched reports, and can write an updated registry JSON when invoked with `--apply --output`.
- **Sections dashboard YAML**: When editing a sections-based dashboard via the UI, the root keys must be `title:` and `sections:` (no `views:` wrapper). The sample `examples/dashboard_qube_overview.yaml` follows this schema.
