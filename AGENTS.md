# Repository Guidelines

## Project Structure & Module Organization
- Root contains JSON file for HACS integration for Home Assistant
- custom_components/ contains the files for the HACS integration
- Place reusable code in `src/` (e.g., parsers, validators); command-line helpers in `scripts/`.
- Add tests in `tests/` mirroring `src/` structure (e.g., `tests/test_validate_config.py`).
- Keep sample fixtures in `tests/fixtures/` and any non-code assets in `assets/`.

## Build, Test, and Development Commands
- Lint YAML: `yamllint conf_modbus.yaml` (ensure two-space indentation, no tabs).
- Run linters/hooks (if configured): `pre-commit run --all-files`.
- Python tests (when present): `pytest -q` from repo root.
- Validate config (example): `python scripts/validate_config.py conf_modbus.yaml` to check schema and references.

## Coding Style & Naming Conventions
- YAML: two-space indent, lowercase keys in `snake_case`, comments with `#` above the field they describe.
- File names: use `.yaml` (not `.yml`); environment-specific overrides as `conf_modbus.<env>.yaml` (e.g., `conf_modbus.dev.yaml`).
- Python (if added): PEP 8, 88–100 char lines, type hints required in `src/`.

## Testing Guidelines
- Prefer `pytest`; name tests `test_*.py` and functions `test_*`.
- Add schema-based tests for `conf_modbus.yaml` (e.g., using `jsonschema`/`pykwalify`).
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
