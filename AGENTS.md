# Repository Guidelines

Guidelines for coding agents and contributors working on this HACS integration. `CLAUDE.md` only imports this file; keep everything here.

## Layout
- `custom_components/qube_heatpump/` — the HACS integration (the only shipped code).
- `tests/` — pytest suite (`pytest-homeassistant-custom-component`); `tests/fixtures/entity_ids.json` pins entity and unique IDs; `tests/snapshots/` holds the syrupy entity snapshots.
- `wiki/README.md` — user documentation; `manifest.json` `documentation` and the config flow's `DOCS_URL` link to this file in the repository (there is no separate GitHub wiki).
- `examples/` — sample Lovelace dashboard; `assets/` — images referenced by the wiki and dashboard.
- Tooling config (ruff, pytest, mypy) is in `pyproject.toml`.

## External library: python-qube-heatpump
- Register addresses, data types, scaling and entity keys are defined in the
  [python-qube-heatpump](https://github.com/MattieGit/python-qube-heatpump) library
  (`entities/sensors.py`, `binary_sensors.py`, `switches.py`), not in this repo.
  Change entities there first, release to PyPI, then raise the `>=` pin in `manifest.json` and
  `requirements_test.txt`.
- The library also reads the controller's mDNS record (`async_get_device_info`, `parse_device_info`)
  and validates a host (`async_verify_device`); the core integration `hr_energy_qube` uses the same library
  with an exact `==` pin.
- The library key doubles as `vendor_id` and `translation_key` in the integration.

## Commands
- Tests: `pytest -q` (from the repo root, inside the venv).
- Lint/format: `ruff check custom_components tests` and `ruff format --check custom_components tests` (CI pins ruff 0.14.14).
- HACS validation runs in CI (`hacs/action`); to run it locally use the `ghcr.io/hacs/action:main`
  image with `--platform linux/amd64` on Apple Silicon.
- hassfest in CI also checks the requirement against the pin in the newest core release; it fails while
  this repo requires a newer library than core pins, until core catches up.

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

## Entity ID Naming Convention

Entity IDs in this integration use **vendor_id** as the basis for stable, predictable entity IDs. The vendor_id is the entity key from the [python-qube-heatpump](https://github.com/MattieGit/python-qube-heatpump) library (`entities/sensors.py`, `binary_sensors.py`, `switches.py`), which also defines the Modbus register behind it.

### How it works

1. `entity_defs._library_to_ha_entity()` maps each library entity to an `EntityDef` and sets `vendor_id` and `translation_key` to the library key
2. Each entity class sets `self.entity_id` to `{platform}.{label}_{vendor_id}`, where `label` is the slugified device name (default "qube 1" → `qube_1`)
3. `tests/fixtures/entity_ids.json` pins every entity ID and unique ID; a change there means existing users get new entity IDs

### Example

| vendor_id | Device Name | Resulting Entity ID |
|-----------|-------------|---------------------|
| `temp_supply` | qube 1 | `sensor.qube_1_temp_supply` |
| `bms_summerwinter` | qube 1 | `switch.qube_1_bms_summerwinter` |
| `tapw_timeprogram_dhwsetp_nolinq` | qube 1 | `number.qube_1_tapw_timeprogram_dhwsetp_nolinq` |

### Benefits

- **Stable**: Entity IDs won't change when translations are updated
- **Predictable**: Direct mapping from the library key to entity_id
- **Short**: Vendor IDs are concise (e.g., `temp_supply` vs `supply_temperature_cv`)
- **Traceable**: Easy to find the register definition in the library from the entity_id

### Implementation

In each entity class (`sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`):

```python
# Use vendor_id for stable, predictable entity IDs
if ent.vendor_id:
    self.entity_id = f"{platform}.{hub.label}_{ent.vendor_id}"
```

For entities without vendor_id (computed sensors, diagnostic sensors), the `translation_key` is used:

```python
self.entity_id = f"sensor.{self._label}_{translation_key}"
```

Fixed entities without a library key set a literal suffix, for example `select.{label}_sg_ready_mode` and `button.{label}_reload`. The climate entity has no explicit entity_id; Home Assistant derives `climate.{label}_thermostat` from its translated name.

**Important:** Use `self.entity_id` (not `_attr_suggested_object_id`) - Home Assistant extracts the object_id from this before entity registration.

### Unique IDs and device identity

- Entity unique IDs are scoped to the config entry: `{entry_id}_{key}` (`QubeEntity._scoped_uid`), and the device identifier is `(DOMAIN, entry_id)`. A host change keeps the device and its entities (since 2026.9.4, config entry version 2).
- The config entry's unique ID is the controller's mDNS `Uuid` when the heat pump answers mDNS, otherwise `qube_heatpump-{host}-{port}`. Entries adopt the uuid on their next start (`_async_adopt_controller_uuid` in `__init__.py`).

### Entity Name vs Entity ID

- **Entity ID** (e.g., `sensor.qube_1_temp_supply`): Based on vendor_id, stable
- **Entity Name** (e.g., "Supply temperature CV"): Based on translation, user-friendly

Both `_attr_has_entity_name = True` and `translation_key` are used so the UI shows translated names while entity IDs remain stable.
