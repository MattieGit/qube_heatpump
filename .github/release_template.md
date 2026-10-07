# Qube heat pump – Release ${VERSION}

Date: ${DATE}

Release notes are the `CHANGELOG.md` entry for this version. Create the release as a pre-release
(`gh release create v${VERSION} --prerelease --notes-file <entry>`) and promote it to Latest once it
is confirmed on a device.

## Summary
- Short description of the release and the main goals.

## Changes
- Copy the `CHANGELOG.md` entry (`feat:`, `fix:`, `chore:` lines).

## Breaking changes
- [ ] Describe any breaking change and migration steps (for example a config entry version bump).

## Requirements
- python-qube-heatpump version required by `manifest.json` (installed automatically).

## Installation / Update
- HACS (recommended):
  - If not installed yet: HACS → three-dot menu → **Custom repositories** → add this repository as
    category **Integration**, then install **Qube heat pump**.
  - Restart Home Assistant after installing or updating.
  - On the same network the heat pump is discovered automatically; otherwise add it via
    **Settings → Devices & services → Add integration → Qube heat pump**.
- Manual install:
  - Copy `custom_components/qube_heatpump/` into `<config>/custom_components/qube_heatpump/`.
  - Restart Home Assistant and add the integration from the UI as above.

## Validation steps
- The device appears with its entities (`tests/fixtures/entity_ids.json` lists all of them).
- Toggle a switch and verify the state refreshes.
- Download diagnostics and check `firmware_version` and the `mdns` section.
- Check the logs for errors from `custom_components.qube_heatpump` or `python_qube_heatpump`.

## Known issues
- List known issues or limitations.

## Checks
- [ ] Tests pass
- [ ] hassfest passes (or fails only on the core requirement pin)
- [ ] HACS validation passes
- [ ] Verified against a device
