# WP Qube Heatpump – Release ${VERSION}

Date: ${DATE}

## Summary
- Short description of the release and the main goals.

## Highlights
- Bullet 1
- Bullet 2

## Breaking Changes
- [ ] Describe any breaking change and migration steps

## Changes
- Link issues/PRs or summarize notable changes

## Installation / Update
- HACS (recommended):
  - Ensure HACS is installed in Home Assistant.
  - In Home Assistant, go to `HACS → Integrations`.
  - If not installed yet: click the three‑dot menu → `Custom repositories` → add this repo URL as category `Integration`, then install "WP Qube Heatpump".
  - After install/update, restart Home Assistant if prompted.
  - Add or reconfigure the integration via `Settings → Devices & Services → Add Integration → WP Qube Heatpump`.

- Manual install:
  - Copy the `custom_components/wp_qube/` folder into `<config>/custom_components/wp_qube/`.
  - Restart Home Assistant.
  - Add the integration from the UI as above.

## Configuration
- Enter the heat pump IP and (optional) port (default 502).
- The bundled `modbus.yaml` defines sensors/binary sensors/switches. The IP/host in that file is ignored at runtime and replaced by the value you enter in the config flow.

## Validation Steps
- Confirm a device appears with ~35 binary sensors, ~41 sensors, and 9 switches.
- Toggle a switch and verify state refresh.
- Check logs for errors from `wp_qube` or `modbus`.

## Known Issues
- List known issues or limitations.

## Checks
- [ ] hassfest passes
- [ ] HACS validation passes
- [ ] Basic connectivity verified against a device

