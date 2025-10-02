from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable loading of custom components during tests."""

    yield


class _DummyModbusException(Exception):
    """Fallback Modbus exception used by tests."""


class _DummyAsyncModbusTcpClient:
    """Minimal async Modbus client stub for unit tests."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.connected = True

    async def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:  # pragma: no cover - simple stub
        self.connected = False


@pytest.fixture(autouse=True)
def patch_pymodbus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a lightweight pymodbus stub so imports succeed in tests."""

    client = SimpleNamespace(AsyncModbusTcpClient=_DummyAsyncModbusTcpClient)
    exceptions = SimpleNamespace(ModbusException=_DummyModbusException)
    module = SimpleNamespace(client=client, exceptions=exceptions)

    monkeypatch.setitem(sys.modules, "pymodbus", module)
    monkeypatch.setitem(sys.modules, "pymodbus.client", client)
    monkeypatch.setitem(sys.modules, "pymodbus.exceptions", exceptions)

    yield

    for name in ("pymodbus", "pymodbus.client", "pymodbus.exceptions"):
        sys.modules.pop(name, None)
