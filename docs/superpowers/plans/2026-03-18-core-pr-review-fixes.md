# Core PR Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address @joostlek's review on home-assistant/core#160409 by simplifying the integration and moving connection resilience into the library.

**Architecture:** Library (`python-qube-heatpump`) owns all Modbus communication including auto-reconnect with backoff, software version read, and MAC address lookup. Integration (`homeassistant/components/qube_heatpump`) becomes a thin HA adapter: config flow validates device and gets MAC for unique ID, coordinator fetches data and applies clamping, entities use `_attr_device_info`.

**Tech Stack:** Python 3.12+, pymodbus >=3.11.0, pytest + pytest-asyncio, Home Assistant core test framework

**Spec:** `docs/superpowers/specs/2026-03-18-core-pr-review-fixes-design.md`

---

## Chunk 1: Library Changes

All work in `/Users/matthijskeij/Github/python-qube-heatpump`.

### Task 1: Add software version register constant and read method

**Files:**
- Modify: `src/python_qube_heatpump/const.py`
- Modify: `src/python_qube_heatpump/client.py`
- Modify: `src/python_qube_heatpump/__init__.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Add SOFTWARE_VERSION constant to const.py**

```python
# At end of const.py, after USER_DHW_SETPOINT
SOFTWARE_VERSION = (77, ModbusType.INPUT, DataType.FLOAT32, None, None)
```

- [ ] **Step 2: Write failing test for async_get_software_version**

In `tests/test_client.py`:

```python
@pytest.mark.asyncio
async def test_get_software_version(mock_modbus_client):
    """Test reading software version."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value

    # Mock response for version 2.15 as FLOAT32
    # 2.15 ≈ 0x4009999A -> regs[0]=0x4009=16393, regs[1]=0x999A=39322
    mock_resp = MagicMock()
    mock_resp.isError.return_value = False
    mock_resp.registers = [16393, 39322]

    mock_instance.read_input_registers = AsyncMock(return_value=mock_resp)
    client._client = mock_instance

    result = await client.async_get_software_version()
    assert result is not None
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_get_software_version_error(mock_modbus_client):
    """Test software version returns None on error."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value

    mock_resp = MagicMock()
    mock_resp.isError.return_value = True

    mock_instance.read_input_registers = AsyncMock(return_value=mock_resp)
    client._client = mock_instance

    result = await client.async_get_software_version()
    assert result is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/test_client.py::test_get_software_version -v`
Expected: FAIL with `AttributeError: 'QubeClient' object has no attribute 'async_get_software_version'`

- [ ] **Step 4: Implement async_get_software_version in client.py**

Add to `QubeClient` class after `get_all_data()`:

```python
async def async_get_software_version(self) -> str | None:
    """Read the software version from the device.

    Reads InputRegister 77 (GeneralMng.Softversion).

    Returns:
        Version as string (e.g., "2.15"), or None on error.
    """
    value = await self.read_value(const.SOFTWARE_VERSION)
    if value is None:
        return None
    return str(round(value, 2))
```

- [ ] **Step 5: Export from __init__.py — no change needed**

`async_get_software_version` is a method on `QubeClient` which is already exported.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/test_client.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/matthijskeij/Github/python-qube-heatpump
git add src/python_qube_heatpump/const.py src/python_qube_heatpump/client.py tests/test_client.py
git commit -m "feat: add async_get_software_version method"
```

### Task 2: Add auto-reconnect with exponential backoff

**Files:**
- Modify: `src/python_qube_heatpump/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for auto-reconnect**

In `tests/test_client.py`:

```python
@pytest.mark.asyncio
async def test_ensure_connected_reconnects(mock_modbus_client):
    """Test _ensure_connected reconnects when disconnected."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value
    mock_instance.connect.return_value = True
    client._client = mock_instance
    client._connected = False

    await client._ensure_connected()
    assert client._connected is True
    mock_instance.connect.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_connected_skips_when_connected(mock_modbus_client):
    """Test _ensure_connected does nothing when already connected."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value
    client._client = mock_instance
    client._connected = True

    await client._ensure_connected()
    mock_instance.connect.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_connected_backoff(mock_modbus_client):
    """Test _ensure_connected applies exponential backoff on failure."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value
    mock_instance.connect.return_value = False
    client._client = mock_instance
    client._connected = False

    # First failure — backoff starts at 1s
    await client._ensure_connected()
    assert client._connected is False
    assert client._backoff_seconds == 1.0

    # Second failure — backoff doubles to 2s
    client._next_connect_at = 0  # bypass wait for test
    await client._ensure_connected()
    assert client._backoff_seconds == 2.0


@pytest.mark.asyncio
async def test_ensure_connected_backoff_resets_on_success(mock_modbus_client):
    """Test backoff resets after successful connect."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value
    client._client = mock_instance
    client._connected = False
    client._backoff_seconds = 16.0

    mock_instance.connect.return_value = True
    await client._ensure_connected()
    assert client._connected is True
    assert client._backoff_seconds == 0.0


@pytest.mark.asyncio
async def test_get_all_data_auto_reconnects(mock_modbus_client):
    """Test get_all_data calls _ensure_connected before reading."""
    client = QubeClient("1.2.3.4", 502)
    mock_instance = mock_modbus_client.return_value
    mock_instance.connect.return_value = True
    client._client = mock_instance
    client._connected = False

    # Mock successful register reads
    mock_resp = MagicMock()
    mock_resp.isError.return_value = False
    mock_resp.registers = [0, 0]
    mock_instance.read_input_registers = AsyncMock(return_value=mock_resp)
    mock_instance.read_holding_registers = AsyncMock(return_value=mock_resp)

    state = await client.get_all_data()
    assert state is not None
    # Verify connect was called (auto-reconnect happened)
    mock_instance.connect.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/test_client.py::test_ensure_connected_reconnects -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement auto-reconnect in client.py**

Add backoff state to `__init__`:

```python
def __init__(self, host: str, port: int = 502, unit_id: int = 1):
    """Initialize."""
    self.host = host
    self.port = port
    self.unit = unit_id
    self._client = AsyncModbusTcpClient(host, port=port)
    self._connected = False
    # Backoff state
    self._backoff_seconds: float = 0.0
    self._backoff_max: float = 60.0
    self._next_connect_at: float = 0.0
```

Add `_ensure_connected` method and `import time` at top of file:

```python
async def _ensure_connected(self) -> None:
    """Ensure connection is active, reconnecting with backoff if needed."""
    if self._connected:
        return

    now = time.monotonic()
    if now < self._next_connect_at:
        return

    result = await self._client.connect()
    if result:
        self._connected = True
        self._backoff_seconds = 0.0
        self._next_connect_at = 0.0
    else:
        self._backoff_seconds = min(
            self._backoff_max, max(1.0, self._backoff_seconds * 2)
        )
        self._next_connect_at = now + self._backoff_seconds
```

Modify `get_all_data()` to call `_ensure_connected()` at the top:

```python
async def get_all_data(self) -> QubeState:
    """Fetch all definition data and return a state object."""
    await self._ensure_connected()
    if not self._connected:
        return None

    state = QubeState()
    # ... rest unchanged ...
```

Update `close()` to reset backoff:

```python
async def close(self) -> None:
    """Close connection."""
    self._client.close()
    self._connected = False
    self._backoff_seconds = 0.0
    self._next_connect_at = 0.0
```

Update `get_all_data` return type to `QubeState | None`.

- [ ] **Step 4: Run all tests**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/test_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/matthijskeij/Github/python-qube-heatpump
git add src/python_qube_heatpump/client.py tests/test_client.py
git commit -m "feat: add auto-reconnect with exponential backoff"
```

### Task 3: Add MAC address lookup utility

**Files:**
- Create: `src/python_qube_heatpump/network.py`
- Modify: `src/python_qube_heatpump/__init__.py`
- Create: `tests/test_network.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_network.py`:

```python
"""Test network utilities."""

from unittest.mock import AsyncMock, mock_open, patch

import pytest

from python_qube_heatpump.network import async_get_mac_address


ARP_TABLE_CONTENT = """\
IP address       HW type     Flags       HW address            Mask     Device
192.168.5.208    0x1         0x2         00:0a:5c:94:83:15     *        eth0
192.168.5.1      0x1         0x2         d0:21:f9:5d:dd:2f     *        eth0
"""


@pytest.mark.asyncio
async def test_get_mac_address():
    """Test MAC address lookup from ARP table."""
    with (
        patch(
            "python_qube_heatpump.network.asyncio.open_connection",
            return_value=(AsyncMock(), AsyncMock()),
        ),
        patch(
            "python_qube_heatpump.network._resolve_ip",
            return_value="192.168.5.208",
        ),
        patch(
            "builtins.open",
            mock_open(read_data=ARP_TABLE_CONTENT),
        ),
    ):
        result = await async_get_mac_address("qube.local")

    assert result == "00:0a:5c:94:83:15"


@pytest.mark.asyncio
async def test_get_mac_address_not_found():
    """Test MAC address returns None when not in ARP table."""
    with (
        patch(
            "python_qube_heatpump.network.asyncio.open_connection",
            return_value=(AsyncMock(), AsyncMock()),
        ),
        patch(
            "python_qube_heatpump.network._resolve_ip",
            return_value="192.168.5.99",
        ),
        patch(
            "builtins.open",
            mock_open(read_data=ARP_TABLE_CONTENT),
        ),
    ):
        result = await async_get_mac_address("unknown.local")

    assert result is None


@pytest.mark.asyncio
async def test_get_mac_address_connection_fails():
    """Test MAC address returns None when connection fails."""
    with (
        patch(
            "python_qube_heatpump.network.asyncio.open_connection",
            side_effect=OSError,
        ),
        patch(
            "python_qube_heatpump.network._resolve_ip",
            return_value="192.168.5.208",
        ),
    ):
        result = await async_get_mac_address("qube.local")

    assert result is None


@pytest.mark.asyncio
async def test_get_mac_address_no_proc_net_arp():
    """Test MAC address returns None on non-Linux systems."""
    with (
        patch(
            "python_qube_heatpump.network.asyncio.open_connection",
            return_value=(AsyncMock(), AsyncMock()),
        ),
        patch(
            "python_qube_heatpump.network._resolve_ip",
            return_value="192.168.5.208",
        ),
        patch(
            "builtins.open",
            side_effect=FileNotFoundError,
        ),
    ):
        result = await async_get_mac_address("qube.local")

    assert result is None


@pytest.mark.asyncio
async def test_get_mac_address_with_ip_directly():
    """Test MAC address lookup when given an IP directly."""
    with (
        patch(
            "python_qube_heatpump.network.asyncio.open_connection",
            return_value=(AsyncMock(), AsyncMock()),
        ),
        patch(
            "python_qube_heatpump.network._resolve_ip",
            return_value="192.168.5.208",
        ),
        patch(
            "builtins.open",
            mock_open(read_data=ARP_TABLE_CONTENT),
        ),
    ):
        result = await async_get_mac_address("192.168.5.208")

    assert result == "00:0a:5c:94:83:15"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/test_network.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement network.py**

Create `src/python_qube_heatpump/network.py`:

```python
"""Network utilities for Qube Heat Pump."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket

_LOGGER = logging.getLogger(__name__)

MODBUS_PORT = 502


def _resolve_ip(host: str) -> str | None:
    """Resolve hostname to IP address."""
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _read_arp_table(ip: str) -> str | None:
    """Read MAC address from /proc/net/arp for the given IP.

    Only works on Linux. Returns None on other platforms.
    """
    try:
        with open("/proc/net/arp") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    mac = parts[3]
                    if mac != "00:00:00:00:00:00":
                        return mac.lower()
    except FileNotFoundError:
        _LOGGER.debug("/proc/net/arp not found — not running on Linux")
    return None


async def async_get_mac_address(host: str, port: int = MODBUS_PORT) -> str | None:
    """Get the MAC address of a device by connecting and reading ARP.

    Opens a brief TCP connection to populate the ARP table, then reads
    the MAC address from /proc/net/arp.

    Only works on Linux (where /proc/net/arp exists). Returns None on
    other platforms or if the device is not on the same L2 network.

    Args:
        host: Hostname or IP address of the device.
        port: TCP port to connect to (default: 502 for Modbus).

    Returns:
        MAC address as lowercase colon-separated string, or None.
    """
    ip = _resolve_ip(host)
    if ip is None:
        _LOGGER.debug("Could not resolve host %s to IP", host)
        return None

    # Open a brief TCP connection to populate ARP table
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=5
        )
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    except (OSError, TimeoutError):
        _LOGGER.debug("Could not connect to %s:%s to populate ARP", ip, port)
        return None

    return _read_arp_table(ip)
```

- [ ] **Step 4: Export from __init__.py**

Add to `src/python_qube_heatpump/__init__.py`:

```python
from .network import async_get_mac_address
```

And add `"async_get_mac_address"` to the `__all__` list.

- [ ] **Step 5: Run tests**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/matthijskeij/Github/python-qube-heatpump
git add src/python_qube_heatpump/network.py src/python_qube_heatpump/__init__.py tests/test_network.py
git commit -m "feat: add MAC address lookup utility"
```

### Task 4: Bump library version and release

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version to 1.6.0**

In `pyproject.toml`, change:
```
version = "1.5.4"
```
to:
```
version = "1.6.0"
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/matthijskeij/Github/python-qube-heatpump && .venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit and push**

```bash
cd /Users/matthijskeij/Github/python-qube-heatpump
git add pyproject.toml
git commit -m "chore: bump version to 1.6.0"
git push origin main
```

- [ ] **Step 4: Create GitHub release to trigger PyPI publish**

```bash
cd /Users/matthijskeij/Github/python-qube-heatpump
gh release create v1.6.0 --title "v1.6.0" --notes "feat: auto-reconnect with backoff, MAC address lookup, software version read"
```

- [ ] **Step 5: Verify PyPI publish**

Wait ~2 min, then check: `pip index versions python-qube-heatpump`
Expected: `1.6.0` appears in the list.

---

## Chunk 2: Integration Changes — Config Flow and Setup

All work in `/Users/matthijskeij/Github/core` on branch `add-qube-heatpump`.

### Task 5: Remove AGENTS.md, hub.py, and update const.py

**Files:**
- Delete: `homeassistant/components/qube_heatpump/AGENTS.md` (already staged)
- Delete: `homeassistant/components/qube_heatpump/hub.py`
- Modify: `homeassistant/components/qube_heatpump/const.py`
- Delete: `tests/components/qube_heatpump/test_hub.py`

- [ ] **Step 1: Delete hub.py, test_hub.py, and test_integration.py**

AGENTS.md was already staged for deletion in a prior step.

```bash
cd /Users/matthijskeij/Github/core
git rm homeassistant/components/qube_heatpump/hub.py
git rm tests/components/qube_heatpump/test_hub.py
git rm tests/components/qube_heatpump/test_integration.py
```

- [ ] **Step 2: Update const.py — remove CONF_UNIT_ID**

Replace entire `const.py` with:

```python
"""Constants for the Qube Heat Pump integration."""

from homeassistant.const import Platform

DOMAIN = "qube_heatpump"
PLATFORMS = [Platform.SENSOR]

DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 15
```

- [ ] **Step 3: Commit**

```bash
cd /Users/matthijskeij/Github/core
git add -A homeassistant/components/qube_heatpump/
git add tests/components/qube_heatpump/
git commit -m "refactor: remove hub.py, AGENTS.md, and CONF_UNIT_ID"
```

### Task 6: Rewrite config_flow.py

**Files:**
- Rewrite: `homeassistant/components/qube_heatpump/config_flow.py`
- Rewrite: `tests/components/qube_heatpump/test_config_flow.py`
- Modify: `homeassistant/components/qube_heatpump/strings.json`

- [ ] **Step 1: Write new config_flow.py**

```python
"""Config flow for Qube Heat Pump integration."""

from __future__ import annotations

import logging
from typing import Any

from python_qube_heatpump import QubeClient, async_get_mac_address
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class QubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qube Heat Pump."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            # Connect and verify it's a Qube by reading software version
            client = QubeClient(host, DEFAULT_PORT)
            try:
                connected = await client.connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    version = await client.async_get_software_version()
                    if version is None:
                        errors["base"] = "not_qube_device"
            except (OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                # Get MAC address for unique ID
                mac = await async_get_mac_address(host)
                if mac is None:
                    errors["base"] = "mac_not_found"

            if not errors:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Qube Heat Pump",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: DEFAULT_PORT,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="qube.local"): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
```

- [ ] **Step 2: Update strings.json**

Replace entire `strings.json`:

```json
{
  "config": {
    "abort": {
      "already_configured": "[%key:common::config_flow::abort::already_configured_device%]"
    },
    "error": {
      "cannot_connect": "[%key:common::config_flow::error::cannot_connect%]",
      "not_qube_device": "Could not verify this is a Qube heat pump. Check the host address.",
      "mac_not_found": "Could not determine device identity. Ensure the heat pump is on the same network."
    },
    "step": {
      "user": {
        "data": {
          "host": "[%key:common::config_flow::data::host%]"
        },
        "data_description": {
          "host": "The IP address or hostname of your Qube heat pump."
        },
        "description": "Enter the heat pump IP or host.",
        "title": "Qube heat pump"
      }
    }
  },
  "entity": {
    "sensor": {
      "temp_supply": {
        "name": "Supply temperature CH"
      },
      "temp_return": {
        "name": "Return temperature"
      },
      "temp_source_in": {
        "name": "Source temperature in"
      },
      "temp_source_out": {
        "name": "Source temperature out"
      },
      "temp_room": {
        "name": "Room temperature"
      },
      "temp_dhw": {
        "name": "DHW temperature"
      },
      "temp_outside": {
        "name": "Outside temperature"
      },
      "power_thermic": {
        "name": "Thermal power"
      },
      "power_electric": {
        "name": "Electric power"
      },
      "energy_total_electric": {
        "name": "Total electric consumption"
      },
      "energy_total_thermic": {
        "name": "Total thermal yield"
      },
      "cop_calc": {
        "name": "COP"
      },
      "compressor_speed": {
        "name": "Compressor speed"
      },
      "flow_rate": {
        "name": "Measured PVT flow"
      },
      "setpoint_room_heat_day": {
        "name": "Room setpoint heating (day)"
      },
      "setpoint_room_heat_night": {
        "name": "Room setpoint heating (night)"
      },
      "setpoint_room_cool_day": {
        "name": "Room setpoint cooling (day)"
      },
      "setpoint_room_cool_night": {
        "name": "Room setpoint cooling (night)"
      },
      "status_heatpump": {
        "name": "Heat pump status",
        "state": {
          "standby": "[%key:common::state::standby%]",
          "alarm": "Alarm",
          "keyboard_off": "Keyboard off",
          "compressor_startup": "Compressor startup",
          "compressor_shutdown": "Compressor stopping",
          "cooling": "[%key:component::climate::entity_component::_::state_attributes::hvac_action::state::cooling%]",
          "heating": "[%key:component::climate::entity_component::_::state_attributes::hvac_action::state::heating%]",
          "start_fail": "Start failed",
          "heating_dhw": "Heating DHW"
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write new test_config_flow.py**

```python
"""Test the Qube Heat Pump config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.components.qube_heatpump.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

MOCK_MAC = "00:0a:5c:94:83:15"


@pytest.fixture
def mock_qube_setup():
    """Mock QubeClient and MAC lookup for config flow tests."""
    with (
        patch(
            "homeassistant.components.qube_heatpump.config_flow.QubeClient",
            autospec=True,
        ) as mock_client_cls,
        patch(
            "homeassistant.components.qube_heatpump.config_flow.async_get_mac_address",
            return_value=MOCK_MAC,
        ) as mock_mac,
    ):
        client = mock_client_cls.return_value
        client.connect = AsyncMock(return_value=True)
        client.async_get_software_version = AsyncMock(return_value="2.15")
        client.close = AsyncMock()
        yield {"client_cls": mock_client_cls, "client": client, "mac": mock_mac}


async def test_form(
    hass: HomeAssistant, mock_setup_entry: MagicMock, mock_qube_setup: dict
) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "qube.local"},
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Qube Heat Pump"
    assert result2["data"] == {CONF_HOST: "qube.local", CONF_PORT: 502}
    assert result2["result"].unique_id == MOCK_MAC


async def test_form_cannot_connect(
    hass: HomeAssistant, mock_qube_setup: dict
) -> None:
    """Test we handle cannot connect error."""
    mock_qube_setup["client"].connect.return_value = False

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.1.1.1"},
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_connect_exception(
    hass: HomeAssistant, mock_qube_setup: dict
) -> None:
    """Test we handle connection exception."""
    mock_qube_setup["client"].connect.side_effect = OSError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.1.1.1"},
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_not_qube_device(
    hass: HomeAssistant, mock_qube_setup: dict
) -> None:
    """Test we handle device that isn't a Qube."""
    mock_qube_setup["client"].async_get_software_version.return_value = None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.1.1.1"},
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "not_qube_device"}


async def test_form_mac_not_found(
    hass: HomeAssistant, mock_qube_setup: dict
) -> None:
    """Test we handle MAC address not found."""
    mock_qube_setup["mac"].return_value = None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "qube.local"},
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "mac_not_found"}


async def test_form_already_configured(
    hass: HomeAssistant, mock_setup_entry: MagicMock, mock_qube_setup: dict
) -> None:
    """Test we abort when device is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "qube.local"},
    )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
```

- [ ] **Step 4: Run config flow tests**

Run: `cd /Users/matthijskeij/Github/core && python -m pytest tests/components/qube_heatpump/test_config_flow.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/matthijskeij/Github/core
git add homeassistant/components/qube_heatpump/config_flow.py homeassistant/components/qube_heatpump/strings.json tests/components/qube_heatpump/test_config_flow.py
git commit -m "refactor: simplify config flow — MAC unique ID, remove reconfigure"
```

### Task 7: Rewrite __init__.py and entity.py

**Files:**
- Rewrite: `homeassistant/components/qube_heatpump/__init__.py`
- Rewrite: `homeassistant/components/qube_heatpump/entity.py`
- Modify: `tests/components/qube_heatpump/conftest.py`
- Rewrite: `tests/components/qube_heatpump/test_init.py`

- [ ] **Step 1: Write new __init__.py**

```python
"""The Qube Heat Pump integration."""

from __future__ import annotations

from dataclasses import dataclass

from python_qube_heatpump import QubeClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import QubeCoordinator


@dataclass
class QubeData:
    """Runtime data for Qube Heat Pump."""

    coordinator: QubeCoordinator
    client: QubeClient
    sw_version: str | None


type QubeConfigEntry = ConfigEntry[QubeData]


async def async_setup_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Set up Qube Heat Pump from a config entry."""
    client = QubeClient(entry.data[CONF_HOST], entry.data[CONF_PORT])

    # Read software version for device info (best-effort, not critical)
    sw_version: str | None = None
    try:
        await client.connect()
        sw_version = await client.async_get_software_version()
    except (OSError, TimeoutError):
        pass  # Version will be None; coordinator retry handles connectivity

    coordinator = QubeCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = QubeData(
        coordinator=coordinator,
        client=client,
        sw_version=sw_version,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: QubeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.client.close()
    return unload_ok
```

- [ ] **Step 2: Write new entity.py**

```python
"""Base entity for Qube Heat Pump."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import QubeConfigEntry
from .const import DOMAIN
from .coordinator import QubeCoordinator


class QubeEntity(CoordinatorEntity[QubeCoordinator]):
    """Base entity for Qube Heat Pump."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: QubeCoordinator,
        entry: QubeConfigEntry,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Qube",
            model="Heat Pump",
            sw_version=entry.runtime_data.sw_version,
        )
```

- [ ] **Step 3: Update conftest.py**

```python
"""Common fixtures for the Qube Heat Pump tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from python_qube_heatpump.models import QubeState

from homeassistant.components.qube_heatpump.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def get_entity_id_by_unique_id_suffix(
    hass: HomeAssistant, entry_unique_id: str, key: str
) -> str | None:
    """Get entity_id from entity registry by unique_id suffix."""
    entity_registry = er.async_get(hass)
    unique_id = f"{entry_unique_id}-{key}"
    return entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.qube_heatpump.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_qube_state() -> QubeState:
    """Return a mock QubeState object with all properties set."""
    state = QubeState()
    state.temp_supply = 45.0
    state.temp_return = 40.0
    state.temp_outside = 10.0
    state.temp_source_in = 8.0
    state.temp_source_out = 12.0
    state.temp_room = 21.0
    state.temp_dhw = 50.0
    state.power_thermic = 5000.0
    state.power_electric = 1200.0
    state.energy_total_electric = 123.456
    state.energy_total_thermic = 500.0
    state.cop_calc = 4.2
    state.compressor_speed = 3000.0
    state.flow_rate = 15.5
    state.setpoint_room_heat_day = 21.0
    state.setpoint_room_heat_night = 18.0
    state.setpoint_room_cool_day = 25.0
    state.setpoint_room_cool_night = 23.0
    state.status_code = 1
    return state


@pytest.fixture
def mock_qube_client(mock_qube_state: QubeState) -> Generator[MagicMock]:
    """Mock the QubeClient to avoid real network calls."""
    with patch(
        "homeassistant.components.qube_heatpump.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.close = AsyncMock(return_value=None)
        client.get_all_data = AsyncMock(return_value=mock_qube_state)
        client.async_get_software_version = AsyncMock(return_value="2.15")
        yield client
```

- [ ] **Step 4: Write new test_init.py**

```python
"""Test the Qube Heat Pump integration init."""

from unittest.mock import MagicMock

from homeassistant.components.qube_heatpump.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MOCK_MAC = "00:0a:5c:94:83:15"


async def test_async_setup_entry(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test successful setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_async_unload_entry(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test successful unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_qube_client.close.assert_called_once()
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/matthijskeij/Github/core && python -m pytest tests/components/qube_heatpump/test_init.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/matthijskeij/Github/core
git add homeassistant/components/qube_heatpump/__init__.py homeassistant/components/qube_heatpump/entity.py tests/components/qube_heatpump/conftest.py tests/components/qube_heatpump/test_init.py
git commit -m "refactor: simplify __init__.py and entity.py — remove hub dependency"
```

---

## Chunk 3: Integration Changes — Coordinator, Sensor, Quality Scale

### Task 8: Simplify coordinator.py

**Files:**
- Rewrite: `homeassistant/components/qube_heatpump/coordinator.py`
- Rewrite: `tests/components/qube_heatpump/test_coordinator.py`

- [ ] **Step 1: Write new coordinator.py**

```python
"""DataUpdateCoordinator for Qube Heat Pump."""

from __future__ import annotations

from datetime import timedelta
import logging
import math
from typing import TYPE_CHECKING

from python_qube_heatpump import QubeClient
from python_qube_heatpump.models import QubeState

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

MONOTONIC_KEYS = frozenset({"energy_total_electric", "energy_total_thermic"})
CLAMP_MIN_ZERO_KEYS = frozenset({"flow_rate"})


class QubeCoordinator(DataUpdateCoordinator[QubeState]):
    """Qube Heat Pump data coordinator."""

    def __init__(
        self, hass: HomeAssistant, client: QubeClient, entry: ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._previous_values: dict[str, float] = {}
        super().__init__(
            hass,
            _LOGGER,
            name="qube_heatpump",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )

    async def _async_update_data(self) -> QubeState:
        """Fetch data from the device."""
        try:
            data = await self.client.get_all_data()
        except Exception as exc:
            raise UpdateFailed(
                f"Error communicating with Qube heat pump: {exc}"
            ) from exc

        if data is None:
            raise UpdateFailed("No data received from Qube heat pump")

        self._apply_monotonic_clamping(data)
        self._apply_min_zero_clamping(data)
        return data

    def _apply_monotonic_clamping(self, data: QubeState) -> None:
        """Prevent total_increasing sensors from decreasing due to glitches."""
        for key in MONOTONIC_KEYS:
            current = getattr(data, key, None)
            if current is None or not math.isfinite(current):
                continue
            previous = self._previous_values.get(key)
            if previous is not None and current < previous:
                setattr(data, key, previous)
            else:
                self._previous_values[key] = current

    def _apply_min_zero_clamping(self, data: QubeState) -> None:
        """Clamp values that should never be negative."""
        for key in CLAMP_MIN_ZERO_KEYS:
            current = getattr(data, key, None)
            if current is not None and current < 0:
                setattr(data, key, 0.0)
```

- [ ] **Step 2: Write new test_coordinator.py**

```python
"""Test the Qube Heat Pump coordinator."""

from unittest.mock import AsyncMock, MagicMock

from python_qube_heatpump.models import QubeState

from homeassistant.components.qube_heatpump.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MOCK_MAC = "00:0a:5c:94:83:15"


async def test_coordinator_fetches_data(
    hass: HomeAssistant, mock_qube_client: MagicMock, mock_qube_state: QubeState
) -> None:
    """Test coordinator fetches data on setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    mock_qube_client.get_all_data.assert_called()


async def test_coordinator_handles_fetch_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test coordinator handles fetch errors gracefully."""
    mock_qube_client.get_all_data = AsyncMock(side_effect=Exception("Connection lost"))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Entry should still be loaded (coordinator handles the error)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_coordinator_clamps_negative_flow_rate(
    hass: HomeAssistant, mock_qube_client: MagicMock, mock_qube_state: QubeState
) -> None:
    """Test coordinator clamps negative flow rate to 0."""
    mock_qube_state.flow_rate = -0.5
    mock_qube_client.get_all_data = AsyncMock(return_value=mock_qube_state)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    assert coordinator.data.flow_rate == 0.0


async def test_coordinator_monotonic_clamping(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test coordinator prevents total_increasing from decreasing."""
    state1 = QubeState()
    state1.energy_total_electric = 100.0
    state1.energy_total_thermic = 200.0
    state1.status_code = 1

    state2 = QubeState()
    state2.energy_total_electric = 50.0  # glitch: lower than before
    state2.energy_total_thermic = 250.0  # normal increase
    state2.status_code = 1

    mock_qube_client.get_all_data = AsyncMock(side_effect=[state1, state2])

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=MOCK_MAC,
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator

    # First fetch: values accepted as-is
    assert coordinator.data.energy_total_electric == 100.0

    # Trigger second fetch
    await coordinator.async_refresh()

    # Glitch clamped: keeps previous value
    assert coordinator.data.energy_total_electric == 100.0
    # Normal increase: accepted
    assert coordinator.data.energy_total_thermic == 250.0
```

- [ ] **Step 3: Run coordinator tests**

Run: `cd /Users/matthijskeij/Github/core && python -m pytest tests/components/qube_heatpump/test_coordinator.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/matthijskeij/Github/core
git add homeassistant/components/qube_heatpump/coordinator.py tests/components/qube_heatpump/test_coordinator.py
git commit -m "refactor: simplify coordinator — direct QubeClient usage"
```

### Task 9: Update sensor.py

**Files:**
- Modify: `homeassistant/components/qube_heatpump/sensor.py`
- Modify: `tests/components/qube_heatpump/test_sensor.py`

- [ ] **Step 1: Update sensor.py constructor**

Replace the `QubeSensor.__init__` and `QubeStatusSensor.__init__` to use the new `QubeEntity` signature (just `coordinator` and `entry`):

```python
class QubeSensor(QubeEntity, SensorEntity):
    """Qube generic sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: QubeCoordinator,
        entry: QubeConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}-{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return native value."""
        data: QubeState = self.coordinator.data
        if not data:
            return None
        return getattr(data, self.entity_description.key, None)


class QubeStatusSensor(QubeEntity, SensorEntity):
    """Heat pump status sensor with enum device class."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "status_heatpump"
    _attr_options = [
        "standby",
        "alarm",
        "keyboard_off",
        "compressor_startup",
        "compressor_shutdown",
        "cooling",
        "heating",
        "start_fail",
        "heating_dhw",
    ]

    def __init__(
        self,
        coordinator: QubeCoordinator,
        entry: QubeConfigEntry,
    ) -> None:
        """Initialize status sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}-status_heatpump"

    @property
    def native_value(self) -> str | None:
        """Return the status as a string for enum translation."""
        data: QubeState = self.coordinator.data
        if not data:
            return None
        code = data.status_code
        if code is None:
            return None
        return STATUS_MAP.get(code)
```

Update `async_setup_entry` to pass `entry` instead of hub/version/device_name:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: QubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qube sensors."""
    coordinator = entry.runtime_data.coordinator

    entities: list[SensorEntity] = [
        QubeSensor(coordinator, entry, description)
        for description in SENSOR_TYPES
    ]
    entities.append(QubeStatusSensor(coordinator, entry))

    async_add_entities(entities)
```

Remove unused imports (`QubeHub`, `version`, `device_name`).

- [ ] **Step 2: Update test_sensor.py to use new fixture pattern**

Update `MockConfigEntry` instances to use MAC-based unique_id and remove `CONF_NAME`. Update sensor setup to match new architecture. Remove `test_hub.py` references.

Key changes in test_sensor.py:
- All `MockConfigEntry` use `unique_id=MOCK_MAC` and `data={CONF_HOST: "1.2.3.4", CONF_PORT: 502}`
- Tests verify sensors are created and return correct values
- Device info test verifies `sw_version` comes from the mock client

- [ ] **Step 3: Run sensor tests**

Run: `cd /Users/matthijskeij/Github/core && python -m pytest tests/components/qube_heatpump/test_sensor.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/matthijskeij/Github/core
git add homeassistant/components/qube_heatpump/sensor.py tests/components/qube_heatpump/test_sensor.py
git commit -m "refactor: simplify sensor constructors"
```

### Task 10: Update quality_scale.yaml and manifest.json

**Files:**
- Rewrite: `homeassistant/components/qube_heatpump/quality_scale.yaml`
- Modify: `homeassistant/components/qube_heatpump/manifest.json`
- Delete: `tests/components/qube_heatpump/test_integration.py` (if empty/unused)

- [ ] **Step 1: Write complete quality_scale.yaml**

```yaml
rules:
  # Bronze
  action-setup:
    status: exempt
    comment: Integration does not register custom actions.
  appropriate-polling: done
  brands: done
  common-modules: done
  config-flow: done
  config-flow-test-coverage: done
  dependency-transparency: done
  docs-actions:
    status: exempt
    comment: Integration does not register custom actions.
  docs-high-level-description: done
  docs-installation-instructions: done
  docs-removal-instructions: done
  entity-event-setup:
    status: exempt
    comment: Entities do not subscribe to events.
  entity-unique-id: done
  has-entity-name: done
  runtime-data: done
  test-before-configure: done
  test-before-setup: done
  unique-config-entry: done

  # Silver
  action-exceptions:
    status: exempt
    comment: Integration does not register custom actions.
  config-entry-unloading: done
  docs-configuration-parameters:
    status: exempt
    comment: No configuration options beyond initial setup.
  docs-installation-parameters: done
  entity-unavailable: done
  integration-owner: done
  log-when-unavailable: todo
  parallel-updates: done
  reauthentication-flow:
    status: exempt
    comment: No authentication required for Modbus TCP.
  test-coverage: done

  # Gold
  devices: done
  diagnostics: todo
  discovery-update-info: todo
  discovery: todo
  docs-data-update: todo
  docs-examples: todo
  docs-known-limitations: todo
  docs-supported-devices: todo
  docs-supported-functions: todo
  docs-troubleshooting: todo
  docs-use-cases: todo
  dynamic-devices:
    status: exempt
    comment: Single device per config entry.
  entity-category: todo
  entity-device-class: done
  entity-disabled-by-default: todo
  entity-translations: done
  exception-translations: todo
  icon-translations: todo
  reconfiguration-flow: todo
  repair-issues: todo
  stale-devices:
    status: exempt
    comment: Single device per config entry.

  # Platinum
  async-dependency: done
  inject-websession:
    status: exempt
    comment: Uses Modbus TCP, not HTTP.
  strict-typing: done
```

- [ ] **Step 2: Update manifest.json**

Change the requirements line:

```json
"requirements": ["python-qube-heatpump==1.6.0"]
```

- [ ] **Step 3: Regenerate requirements files**

```bash
cd /Users/matthijskeij/Github/core
python -m script.hassfest --integration-path homeassistant/components/qube_heatpump
```

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/matthijskeij/Github/core && python -m pytest tests/components/qube_heatpump/ -v`
Expected: All tests PASS

- [ ] **Step 5: Run linting**

```bash
cd /Users/matthijskeij/Github/core
ruff check homeassistant/components/qube_heatpump tests/components/qube_heatpump
ruff format --check homeassistant/components/qube_heatpump tests/components/qube_heatpump
```

Expected: No errors

- [ ] **Step 6: Commit and push**

```bash
cd /Users/matthijskeij/Github/core
git add homeassistant/components/qube_heatpump/ tests/components/qube_heatpump/ requirements_all.txt requirements_test_all.txt
git commit -m "refactor: complete review fixes — quality scale, manifest bump"
git push origin add-qube-heatpump
```
