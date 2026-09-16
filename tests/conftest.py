"""Common fixtures for the Qube Heat Pump tests."""

from collections.abc import Generator
import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import (
    HomeAssistantSnapshotExtension,
)
from python_qube_heatpump.entities import BINARY_SENSORS, SENSORS, SWITCHES
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN

LIBRARY_ENTITIES = {**SENSORS, **BINARY_SENSORS, **SWITCHES}
COIL_KEYS = frozenset(BINARY_SENSORS) | frozenset(SWITCHES)

# Value every register reads unless a test says otherwise
DEFAULT_REGISTER_VALUE = 45.0
# Deterministic entry id so storage keys and repair issue ids are stable
MOCK_ENTRY_ID = "01JQUBEHEATPUMP00000000000"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Use the Home Assistant serializer; snapshots live in tests/snapshots."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Register every entity enabled, including the disabled-by-default ones."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.qube_heatpump.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def client_values() -> dict[str, Any]:
    """Register values the mocked client returns, by library key.

    Keys that are missing fall back to 45.0 for registers and False for coils
    and discrete inputs. The mock consults the dict on every read, so a test
    can override a key up front (parametrize ``client_values``) or mutate the
    dict and trigger a poll to simulate the device changing.
    """
    return {}


def read_value(client_values: dict[str, Any], key: str) -> Any:
    """Return the mocked reading for a library key."""
    if key in client_values:
        return client_values[key]
    return False if key in COIL_KEYS else DEFAULT_REGISTER_VALUE


@pytest.fixture
def mock_qube_client(client_values: dict[str, Any]) -> Generator[MagicMock]:
    """Mock the library client the hub creates.

    Reads come from ``client_values``; successful writes land in the same
    dict so the next poll reflects them, like a real controller would.
    Monotonic clamping is a plain dict with the library's jitter rule.
    """
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = True
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)
        client.async_get_software_version = AsyncMock(return_value="4.10")

        async def _read_entity(ent: Any) -> Any:
            return read_value(client_values, ent.key)

        async def _get_all_entities() -> dict[str, Any]:
            # Resolved through read_entity so a test may replace either one
            return {
                key: await client.read_entity(ent)
                for key, ent in LIBRARY_ENTITIES.items()
            }

        async def _write(key: str, value: Any) -> bool:
            client_values[key] = value
            return True

        client.read_entity = AsyncMock(side_effect=_read_entity)
        client.get_all_entities = AsyncMock(side_effect=_get_all_entities)
        client.write_switch = AsyncMock(side_effect=_write)
        client.write_setpoint = AsyncMock(side_effect=_write)

        client.monotonic_cache = {}

        def _clamp(key: str, value: float | None) -> float | None:
            if value is None or not math.isfinite(value):
                return value
            previous = client.monotonic_cache.get(key)
            if previous is not None and value < previous:
                return previous
            client.monotonic_cache[key] = value
            return value

        client.clamp_monotonic = MagicMock(side_effect=_clamp)
        client.clear_monotonic_cache = MagicMock(
            side_effect=lambda: client.monotonic_cache.clear()
        )
        yield client


@pytest.fixture
def config_entry_options() -> dict[str, Any]:
    """Options of the mock config entry; override per module or test."""
    return {}


@pytest.fixture
def mock_config_entry(config_entry_options: dict[str, Any]) -> MockConfigEntry:
    """Return a config entry for host 1.2.3.4.

    It carries no name, so setup assigns the default "qube 1" and every
    entity id starts with ``qube_1_`` (see tests/snapshots/entity_ids.json).
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options=config_entry_options,
        entry_id=MOCK_ENTRY_ID,
    )
