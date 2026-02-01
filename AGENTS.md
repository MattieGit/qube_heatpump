# Repository Guidelines

## Project Structure & Module Organization
- Root contains JSON file for HACS integration for Home Assistant with name "qube_heatpump".
- Documentation for publishing a HACS integration can be found via this link: https://www.hacs.xyz/docs/publish/integration/
- Keep the manifest `documentation` URL pointing at the project wiki (https://github.com/MattieGit/qube_heatpump/wiki) so HA and HACS surface it.
- custom_components/ contains the files for the HACS integration
- Place reusable code in `src/` (e.g., parsers, validators); command-line helpers in `scripts/`.
- Add tests in `tests/` mirroring `src/` structure (e.g., `tests/test_validate_config.py`).
- Keep sample fixtures in `tests/fixtures/` and any non-code assets in `assets/`.

## External Library: python-qube-heatpump

This integration depends on the **python-qube-heatpump** library, which is a separate PyPI package maintained in a sibling repository.

### Library Repository
- **GitHub**: https://github.com/MattieGit/python-qube-heatpump
- **PyPI**: https://pypi.org/project/python-qube-heatpump/
- **Local path** (when working on both): `/Users/matthijskeij/Github/python-qube-heatpump`

### Relationship Between Library and Integration
| Component | Repository | Purpose |
|-----------|------------|---------|
| `python-qube-heatpump` | python-qube-heatpump | Low-level async Modbus client for Qube heat pumps. Handles connection, register reading/writing, FLOAT32 decoding (big endian ABCD), entity definitions. |
| `qube_heatpump` | qube_heatpump (this repo) | Home Assistant HACS integration. Uses the library for Modbus communication, adds HA-specific entity classes, translations, config flow, coordinator pattern. |

### Version Synchronization
- The integration's `manifest.json` specifies the minimum required library version in `requirements`.
- When making changes to the library that affect the integration:
  1. Make and test changes in `python-qube-heatpump`
  2. Run `ruff check . && ruff format --check .` and `pytest` before committing
  3. Bump version in library's `pyproject.toml`, commit, tag (e.g., `v1.4.8`), and push
  4. Create GitHub release to trigger PyPI publish
  5. Update `manifest.json` in this integration to require the new version
  6. Bump integration version and release

### Key Library Components Used by Integration
- `QubeClient`: Async Modbus TCP client for connecting and reading/writing registers
- `EntityDef`: Dataclass defining sensors, binary sensors, switches with addresses, data types, scaling
- `SENSORS`, `BINARY_SENSORS`, `SWITCHES`: Pre-defined entity dictionaries from `entities/` module
- `DataType`, `InputType`, `Platform`: Enums for entity configuration

### Common Issues
- **Byte order**: Library uses big endian (ABCD) for FLOAT32: `int_val = (regs[0] << 16) | regs[1]`
- **Percentage scaling**: Pump sensors scale 0-1 raw values to 0-100% via `scale=100.0`
- **Test failures after library changes**: Ensure test mock data matches the byte order used in client.py

## Build, Test, and Development Commands
- Run linters/hooks (if configured): `pre-commit run --all-files`.
- Lint and format Python: `ruff check . && ruff format --check .` (run before committing).
- Python tests: `pytest -q` from repo root (run before committing).
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
- Python: PEP 8, 88–100 char lines, type hints required. Use `ruff` for linting and formatting.

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
- When adding or changing any user-facing names (entities, sensors, switches, buttons, diagnostics), update the translations in `custom_components/qube_heatpump/strings.json` (source) and `translations/*.json` files to keep the UI consistent.

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
- Library-based entity definitions
  - Entity definitions (sensors, binary sensors, switches) are loaded from the `python-qube-heatpump` library via `load_library_entities()`.
  - Modbus register addresses, data types, scaling, and unique_ids are defined in the library, not YAML files.
  - The integration handles Home Assistant-specific concerns: entity classes, translations, coordinator, config flow.

- Unique IDs and naming
  - Prefer vendor-provided unique IDs from the library's `EntityDef` where available.
  - When multiple hubs exist, append a hub label (e.g., `qube1`, displayed as "qube 1") to avoid collisions.
  - Entity IDs prefer "vendor_id + label" where possible; conflicts are avoided if an entity_id already exists.

- Diagnostics
  - Diagnostic "Qube info" sensor: keeps attributes like version, label, host, unit, error counters, and entity counts.
  - Dedicated metric sensors added so users can mark them as Preferred on the device page:
    - `Qube connect errors`, `Qube read errors`, `Qube sensor count`, `Qube binary sensor count`, `Qube switch count`.
  - When more than one device is configured, Diagnostics friendly names automatically include the hub label suffix.

- Device Info
  - `sw_version` is populated from `manifest.json` across all entity platforms (sensors, binary_sensors, switches, buttons).

- Options Flow
  - Added an option `show_label_in_name` (“Show hub label in entity names”).
  - Effective only when multiple heat pumps exist; single-device setups keep names unchanged.
  - Config and options forms should include a short link to the wiki for additional guidance.

## Release & Versioning
- Workflow: `.github/workflows/release.yml` creates GitHub Releases on tags matching `20YY.M.N` and marks them as pre-releases.
- Manifest version is kept in `custom_components/qube_heatpump/manifest.json`.
- Uses Calendar Versioning based on the current date (e.g., Jan 4 2026 → `2026.1.4`).
- Tag and manifest version must remain in sync.

## Files of Interest
- `custom_components/qube_heatpump/__init__.py`
  - Entry point; sets up coordinator, hub, and forwards to platforms.
  - Loads entity definitions from library via `hub.load_library_entities()`.
  - Tracks multi-device state and exposes flags used by platforms:
    - `apply_label_in_name`, `multi_device`.

- `custom_components/qube_heatpump/hub.py`
  - `QubeHub` class wraps the library's `QubeClient` for Modbus communication.
  - `load_library_entities()` imports entity definitions from `python-qube-heatpump`.
  - Handles reading registers, writing setpoints/switches, and error tracking.

- `custom_components/qube_heatpump/coordinator.py`
  - `QubeDataUpdateCoordinator` implements the Home Assistant DataUpdateCoordinator pattern.
  - Polls the hub at regular intervals and provides data to all entities.

- `custom_components/qube_heatpump/config_flow.py`
  - Config flow for creating entries; connectivity check on setup.
  - Options Flow exposes `show_label_in_name` toggle (effective in multi-device setups).

- `custom_components/qube_heatpump/helpers.py`
  - Centralized helper functions: `slugify()`, `suggest_object_id()`, `derive_label_from_title()`.
  - Imported by all platform modules to avoid code duplication.

- Platforms
  - `sensor.py`
    - `QubeInfoSensor` with diagnostics attributes and `sw_version` in Device info.
    - `QubeMetricSensor` (5 dedicated diagnostic metrics; label-suffixed in multi-device setups).
    - `QubeSensor` and `QubeComputedSensor` for library-defined entities.
  - `binary_sensor.py`, `switch.py`, `button.py`, `number.py`, `select.py`
    - Label-aware names; prefer vendor_id + label suggested object_ids.
    - All platforms include `sw_version` in Device info.

- Translations
  - `strings.json` — source translations; generates `translations/*.json` via HA tooling.
  - `translations/en.json`, `translations/nl.json` — entity names and config flow text.

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
1. Bump `version` in `manifest.json` (e.g., `2026.1.5`).
2. Commit the version bump: `git commit -am "chore: bump version to 2026.1.5"`.
3. Create and push a matching tag: `git tag 2026.1.5 && git push origin main --tags`.
4. Create a GitHub Release from the tag to trigger the release workflow.
5. Follow Conventional Commits in PRs/commits for clarity.

## Development Notes
- Keep changes minimal and focused; avoid breaking existing entity_ids whenever possible.
- Prefer vendor `unique_id` adoption when present; use label suffix for disambiguation only on collision.
- For Options Flow or naming changes, reload the config entry to apply name/entity_id updates.
- When modifying entity definitions, make changes in `python-qube-heatpump` library first.

## Open Follow-Ups / TODOs
- Add tests (pytest) for Options Flow behavior, unique_id migrations, and registry cleanup.
- Verify external documentation links (currently point to previous repo path in `manifest.json`).

## Recent Learnings
- **Library-based architecture**: Entity definitions come from `python-qube-heatpump` library, not YAML files. When modifying entities, update the library first, bump its version, release to PyPI, then update the integration's `manifest.json` requirements.
- **Always run linters before committing**: Run `ruff check . && ruff format --check .` and `pytest` in both repos before committing and pushing.
- **Byte order matters**: The library uses big endian (ABCD) for FLOAT32: `int_val = (regs[0] << 16) | regs[1]`. Test mock data must match this byte order.
- **Helper centralization**: Common functions (`slugify`, `suggest_object_id`, `derive_label_from_title`) are in `helpers.py` to avoid duplication across platform modules.
- **Options flow usability**: The Configure cog offers a text input for the Modbus unit ID plus toggles for label display. Multi-device state is derived automatically.
- **Testing expectations**: After significant changes, run `pytest -q`. Tests in `tests/` cover config flow, options flow, and integration setup.
