# Repository Guidelines

Conventions for this codebase live in [CLAUDE.md](CLAUDE.md) (entity ID naming,
task workflow). This file only records facts that are not in CLAUDE.md.

## Layout
- `custom_components/qube_heatpump/` — the HACS integration (the only shipped code).
- `tests/` — pytest suite (`pytest-homeassistant-custom-component`); `tests/snapshots/entity_ids.json` pins entity and unique IDs.
- `wiki/README.md` — user documentation; `manifest.json` `documentation` points at the GitHub wiki, keep it that way.
- `examples/` — sample Lovelace dashboard; `assets/` — images referenced by the wiki and dashboard.
- Tooling config (ruff, pytest, mypy) is in `pyproject.toml`.

## External library: python-qube-heatpump
- Register addresses, data types, scaling and entity keys are defined in the
  [python-qube-heatpump](https://github.com/MattieGit/python-qube-heatpump) library
  (`entities/sensors.py`, `binary_sensors.py`, `switches.py`), not in this repo.
  Change entities there first, release to PyPI, then raise the `>=` pin in `manifest.json`.
- The library key doubles as `vendor_id` and `translation_key` in the integration.

## Commands
- Tests: `pytest -q` (from the repo root, inside the venv).
- Lint/format: `ruff check custom_components tests` and `ruff format --check custom_components tests` (CI pins ruff 0.14.14).
- HACS validation runs in CI (`hacs/action`); to run it locally use the `ghcr.io/hacs/action:main`
  image with `--platform linux/amd64` on Apple Silicon.

## Translations
- `strings.json` is the source; `translations/en.json` and `translations/nl.json` must have the
  same key tree and en.json the same values (`tests/test_strings.py` enforces this and that every
  `entity.<platform>.<key>` is a library key or a `translation_key` used in the code).
- Entity names use sentence case; Dutch uses "SWW" for DHW and "instelpunt" for setpoint.

## Releases
- Calendar versioning `YYYY.M.N` in `manifest.json`; tags are prefixed `v` (e.g. `v2026.9.2`).
- Bump the version, commit, push, then `gh release create vYYYY.M.N --prerelease`. Promote to a
  full release once confirmed on a device. Re-issuing at the same tag does not trigger a HACS
  re-download; bump the version instead.
- Keep `CHANGELOG.md` newest-first and add an entry for every release.

## Commits
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).
- No AI attribution or co-author trailers.
