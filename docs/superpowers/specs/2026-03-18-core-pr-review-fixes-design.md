# Design: Core PR Review Fixes for Qube Heat Pump Integration

**Date:** 2026-03-18
**Context:** Address review feedback from @joostlek on [home-assistant/core#160409](https://github.com/home-assistant/core/pull/160409)
**Repos:** `python-qube-heatpump` (library) and `homeassistant/components/qube_heatpump` (integration)

## Problem

The integration PR received detailed review feedback requesting architectural simplification. The main concerns are:

1. `hub.py` wraps the library with backoff/reconnect logic that belongs in the library itself.
2. Config flow has custom DNS resolution, duplicate detection, and user-settable names that should use HA built-in helpers or be removed.
3. `host:port` is not a valid unique ID — a MAC address should be used instead.
4. Clamping logic in the coordinator belongs in the library.
5. Various code style issues (property vs attribute, unnecessary parameters, dead code).

## Approach

**Clean split**: the library owns all device communication and data quality; the integration is a thin HA adapter. Remove `hub.py` entirely.

## Library Changes (`python-qube-heatpump`)

### Connection Resilience in `QubeClient`

Add auto-reconnect with exponential backoff directly into the client.

- `connect()` remains a single-attempt method for explicit use.
- New internal `_ensure_connected()` method called before every read/write. Reconnects if the connection is down.
- Backoff: starts at 1s, doubles on each consecutive failure, caps at 60s, resets to 0 on successful connection.
- `get_all_data()` calls `_ensure_connected()` automatically, so callers never manage connection state.
- `unit_id` parameter defaults to `1` in the constructor so callers can omit it.

### MAC Address Lookup

New standalone async function in the library: `async_get_mac_address(host: str) -> str | None`

- Resolves hostname to IP if needed (via `socket.getaddrinfo`).
- Opens a brief TCP connection to port 502 to populate the ARP table.
- Reads `/proc/net/arp` (Linux) to find the MAC for that IP.
- Returns normalized MAC string (lowercase, colon-separated) or `None`.
- Only needed during config flow, not on `QubeClient`.

**Platform constraint:** This function reads `/proc/net/arp` and only works on Linux. This is acceptable because Home Assistant production instances run on Linux (HAOS, Docker, supervised). For development on macOS, the function returns `None` and the config flow will fail with a clear error — developers can test with a mocked MAC in unit tests.

Assumption: the Qube is on the same L2 network as the HA host in virtually all deployments. If MAC lookup fails, config flow aborts with an actionable error message explaining the device must be on the same network segment.

### Clamping Logic

Clamping stays in the **integration coordinator**, not the library. Rationale:

- **Monotonic clamping** requires persistent state across HA restarts (to avoid false decreases in `total_increasing` sensors after restart). The library has no persistence mechanism.
- **Min-zero clamping** for `flow_rate` is simple enough to keep alongside the monotonic logic.
- Keeping clamping in the coordinator means the library returns raw data and remains stateless — important for reuse outside HA (CLI tools, scripts).

The coordinator will:
- Apply monotonic clamping for `energy_total_electric` and `energy_total_thermic` using in-memory previous values. On restart, the first value is accepted as-is (HA's `total_increasing` state class handles restart resets gracefully).
- Clamp `flow_rate` to minimum 0.

**Note:** The current HACS integration has disk persistence for the monotonic cache. For the core PR, in-memory clamping is sufficient — `total_increasing` sensors handle HA restarts by design (they detect resets and adjust statistics accordingly). Disk persistence can be added later if needed.

### Software Version Read

New method on `QubeClient`: `async_get_software_version() -> str | None`

- Reads InputRegister 77 (`GeneralMng.Softversion`).
- Returns version as a string.
- Used during config flow to verify the connected device is actually a Qube.
- Also stored in runtime data and passed to `DeviceInfo.sw_version` so the device page shows the firmware version.

### Library Version

These changes constitute a minor version bump (e.g., 1.6.0). Publish to PyPI before updating the integration.

## Integration Changes (`homeassistant/components/qube_heatpump`)

### Remove `hub.py`

Delete entirely. The coordinator uses `QubeClient` directly.

The current hub contains connection management (backoff, reconnect, DNS resolution) and a `get_all_data()` wrapper. Connection resilience moves to the library. The `get_all_data()` call moves to the coordinator. Write functionality (`async_write_switch`, `async_write_setpoint`) is not needed for the initial core submission (sensor-only platform) and is omitted.

### Remove `AGENTS.md`

Already staged for deletion. Added to local `.git/info/exclude`.

### Simplify `__init__.py`

Setup becomes:

```python
async def async_setup_entry(hass, entry):
    client = QubeClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = QubeCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

Removed:
- `CONF_UNIT_ID` and options fallback.
- Integration version fetching via `async_get_loaded_integration`.
- `CONF_NAME` / `device_name` in runtime data.

Runtime data: `QubeCoordinator` (which holds a reference to the client).

### Rework `config_flow.py`

- Import `ConfigFlow` directly instead of `config_entries.ConfigFlow`.
- Remove `_async_resolve_host` and `_async_find_conflicting_entry`. DNS-based duplicate detection (resolving hostnames to compare IPs) is intentionally dropped — HA's standard pattern is exact-match on config data, not resolved-IP comparison. Use `self._async_abort_entries_match({CONF_HOST: host})` for duplicate detection.
- Remove `CONF_NAME` field. HA does not allow user-settable names outside of helpers.
- Remove `async_step_reconfigure` entirely.
- Config flow schema: just `CONF_HOST` with default `qube.local`.
- The config flow hardcodes `CONF_PORT: DEFAULT_PORT` (502) in the entry data dict when creating the entry. Port is not user-configurable but is always stored so `__init__.py` can access it with bracket notation (`entry.data[CONF_PORT]`).

Unique ID flow:
1. User enters host.
2. Connect to device via `QubeClient`.
3. Call `client.async_get_software_version()` to verify it's a Qube (abort with error if it fails).
4. Call `async_get_mac_address(host)` to get MAC (abort with actionable error if it fails).
5. `await self.async_set_unique_id(mac)` then `self._abort_if_unique_id_configured()`.
6. Create entry with title "Qube Heat Pump", data containing `CONF_HOST` and `CONF_PORT`.

### Simplify `coordinator.py`

- Keep monotonic clamping and min-zero clamping here (see Clamping Logic section above).
- Remove `update_method` parameter from `super().__init__()`. Override `_async_update_data` directly.
- Hold reference to `QubeClient` instead of `QubeHub`.
- `_async_update_data`: call `client.get_all_data()`, apply clamping, raise `UpdateFailed` on error.

### Simplify `entity.py`

Replace `device_info` property with `_attr_device_info` assignment in `__init__`:

```python
self._attr_device_info = DeviceInfo(
    identifiers={(DOMAIN, entry.unique_id)},
    name=entry.title,
    manufacturer="Qube",
    model="Heat Pump",
    sw_version=sw_version,
)
```

`sw_version` comes from `async_get_software_version()`, stored in runtime data during setup and passed through to `DeviceInfo`. This shows the actual device firmware version, which is more useful than the integration version.

Remove `_hub`, `_version`, `_device_name` instance variables. Constructor takes only `coordinator` and `entry`.

### Update `sensor.py`

Constructor simplifies to match new `QubeEntity` signature. Entity descriptions unchanged.

### Update `const.py`

Remove `CONF_UNIT_ID`. Keep `DOMAIN`, `PLATFORMS`, `DEFAULT_PORT`, `DEFAULT_SCAN_INTERVAL`.

### Update `strings.json`

- Remove `reconfigure` step and its `abort` reason (`reconfigure_successful`).
- Remove `name` from user step `data` and `data_description`.
- Add error strings for MAC lookup failure (`mac_not_found`) and device verification failure (`not_qube_device`).

### Complete `quality_scale.yaml`

Add all bronze-level rules with correct statuses. Mark inapplicable rules as `exempt` with explanatory comments. Notably, `reconfiguration-flow` should be marked as `todo` (not `done`) since reconfigure is being removed from this PR.

### Update `manifest.json`

Bump `python-qube-heatpump` requirement to `>=1.6.0` (or whatever version includes the library changes).

## Sequencing

1. **Library first**: implement resilience, MAC lookup, version read. Test, release to PyPI.
2. **Integration second**: simplify all files against the new library. Update manifest, push to PR.

## Explicitly Deferred

- **Zeroconf/mDNS discovery**: Qube advertises only as generic Workstation; no specific service type for HA to match on.
- **Reconfigure flow**: per reviewer request. `quality_scale.yaml` marks this as `todo`.
- **`unit_id` configuration**: default value of 1 in library constructor; no known multi-unit deployments.
- **Options flow**: not needed for initial core submission.
- **Write functionality**: switches, setpoints, and number entities are not part of the initial core PR (sensor-only). Write methods from the current hub are omitted.
- **Disk persistence for monotonic cache**: `total_increasing` handles restarts by design. Can be added later if glitches are observed post-restart.
