"""Tests for the Qube Heat Pump hub."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.qube_heatpump.entity_defs import EntityDef
from custom_components.qube_heatpump.hub import QubeHub

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def client() -> Generator[MagicMock]:
    """Patch the library client class and return the instance the hub creates."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.is_connected = False
        instance.connect = AsyncMock(return_value=True)
        instance.close = AsyncMock(return_value=None)
        instance.write_switch = AsyncMock(return_value=True)
        instance.write_setpoint = AsyncMock(return_value=True)
        yield instance


def _switch(unique_id: str = "test_switch") -> EntityDef:
    return EntityDef(
        platform="switch",
        name="test",
        address=100,
        unique_id=unique_id,
        write_type="coil",
        writable=True,
    )


def _setpoint(unique_id: str = "test_setpoint") -> EntityDef:
    return EntityDef(
        platform="sensor",
        name="test",
        address=101,
        unique_id=unique_id,
        input_type="holding",
        writable=True,
    )


async def test_hub_properties(client: MagicMock) -> None:
    """The hub exposes its connection parameters and creates the client eagerly."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    assert hub.host == "1.2.3.4"
    assert hub.port == 502
    assert hub.unit == 1
    assert hub.label == "qube1"
    assert hub.device_name == "qube1"
    assert hub.client is client
    assert hub.resolved_ip is None
    assert hub.err_connect == 0
    assert hub.err_read == 0


@pytest.mark.parametrize(
    ("device_name", "label"),
    [("qube 1", "qube_1"), ("My Qube!", "my_qube"), (None, "qube_heat_pump")],
)
def test_hub_label_is_slug_of_device_name(
    client: MagicMock, device_name: str | None, label: str
) -> None:
    """The label is a stable slug of the device name."""
    assert QubeHub("1.2.3.4", 502, 1, device_name).label == label


async def test_hub_connect_success(client: MagicMock) -> None:
    """A successful connect calls the client once and leaves the counter alone."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    await hub.async_connect()

    client.connect.assert_awaited_once()
    assert hub.err_connect == 0


async def test_hub_connect_skips_when_connected(client: MagicMock) -> None:
    """No reconnect is attempted while the client reports it is connected."""
    client.is_connected = True
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    await hub.async_connect()

    client.connect.assert_not_awaited()


async def test_hub_connect_failure_increments_error(client: MagicMock) -> None:
    """A refused connection raises ConnectionError and counts the failure."""
    client.connect = AsyncMock(return_value=False)
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    with pytest.raises(ConnectionError):
        await hub.async_connect()
    assert hub.err_connect == 1


async def test_hub_connect_exception(client: MagicMock) -> None:
    """A socket error is wrapped in ConnectionError and counted."""
    client.connect = AsyncMock(side_effect=OSError("Network error"))
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    with pytest.raises(ConnectionError, match="Network error"):
        await hub.async_connect()
    assert hub.err_connect == 1


async def test_hub_close(client: MagicMock) -> None:
    """Closing the hub closes the client but keeps it for a later reconnect."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    await hub.async_connect()
    await hub.async_close()

    client.close.assert_awaited_once()
    assert hub.client is client


async def test_hub_resolve_ip_with_ip_address(client: MagicMock) -> None:
    """An IP literal resolves to itself without a DNS lookup."""
    hub = QubeHub("192.168.1.100", 502, 1, "qube1")
    await hub.async_resolve_ip()

    assert hub.resolved_ip == "192.168.1.100"


async def test_hub_resolve_ip_dns(client: MagicMock) -> None:
    """A host name is resolved through getaddrinfo."""
    hub = QubeHub("qube.local", 502, 1, "qube1")
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.getaddrinfo = AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))
            ]
        )
        await hub.async_resolve_ip()

    assert hub.resolved_ip == "192.168.1.50"


async def test_hub_resolve_ip_dns_failure(client: MagicMock) -> None:
    """A failed lookup leaves the resolved IP unset."""
    hub = QubeHub("invalid.host", 502, 1, "qube1")
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.getaddrinfo = AsyncMock(side_effect=OSError)
        await hub.async_resolve_ip()

    assert hub.resolved_ip is None


async def test_hub_resolve_ip_ipv6_mapped(client: MagicMock) -> None:
    """IPv4-mapped IPv6 addresses are unwrapped."""
    hub = QubeHub("qube.local", 502, 1, "qube1")
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.getaddrinfo = AsyncMock(
            return_value=[
                (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::ffff:192.168.1.50", 0))
            ]
        )
        await hub.async_resolve_ip()

    assert hub.resolved_ip == "192.168.1.50"


def test_hub_load_library_entities(client: MagicMock) -> None:
    """All library entities are loaded with the key invariant intact."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.load_library_entities()

    assert len(hub.entities) > 0
    assert all(e.unique_id == e.vendor_id == e.translation_key for e in hub.entities)


def test_hub_inc_read_error(client: MagicMock) -> None:
    """Read errors are counted."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.inc_read_error()
    hub.inc_read_error()

    assert hub.err_read == 2


async def test_hub_write_switch_success(client: MagicMock) -> None:
    """Switch writes go to the library by entity key."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    await hub.async_write_switch(_switch(), True)

    client.write_switch.assert_awaited_once_with("test_switch", True)


async def test_hub_write_switch_failure(client: MagicMock) -> None:
    """A rejected switch write raises ConnectionError."""
    client.write_switch = AsyncMock(return_value=False)
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    with pytest.raises(ConnectionError, match="Failed to write switch"):
        await hub.async_write_switch(_switch(), True)


async def test_hub_write_setpoint_success(client: MagicMock) -> None:
    """Setpoint writes go to the library by entity key."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    await hub.async_write_setpoint(_setpoint(), 21.5)

    client.write_setpoint.assert_awaited_once_with("test_setpoint", 21.5)


async def test_hub_write_setpoint_failure(client: MagicMock) -> None:
    """A rejected setpoint write raises ConnectionError."""
    client.write_setpoint = AsyncMock(return_value=False)
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    with pytest.raises(ConnectionError, match="Failed to write setpoint"):
        await hub.async_write_setpoint(_setpoint(), 21.5)


async def test_hub_write_register_dispatches_by_platform(client: MagicMock) -> None:
    """write_register routes to the setpoint or switch write for the address."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.entities = [_switch(), _setpoint()]

    await hub.async_write_register(101, 21.5)
    client.write_setpoint.assert_awaited_once_with("test_setpoint", 21.5)

    await hub.async_write_register(100, 1)
    client.write_switch.assert_awaited_once_with("test_switch", True)


async def test_hub_write_register_library_entity(client: MagicMock) -> None:
    """write_register works for a real writable library register."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.load_library_entities()
    ent = next(e for e in hub.entities if e.writable and e.platform == "sensor")

    await hub.async_write_register(ent.address, 21.5)
    client.write_setpoint.assert_awaited_once_with(ent.unique_id, 21.5)


async def test_hub_write_register_rejects_unknown_address(client: MagicMock) -> None:
    """An address without a writable entity is a ValueError, not a write."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.load_library_entities()

    with pytest.raises(ValueError, match="No writable entity found"):
        await hub.async_write_register(99999, 42)
    client.write_setpoint.assert_not_awaited()
    client.write_switch.assert_not_awaited()


@pytest.mark.parametrize("value", [0.4, 2, -1])
async def test_hub_write_register_rejects_non_boolean_coil_value(
    client: MagicMock, value: float
) -> None:
    """Coils only accept 0 or 1; nothing is written otherwise."""
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")
    hub.entities = [_switch()]

    with pytest.raises(ValueError, match="only accepts 0 or 1"):
        await hub.async_write_register(100, value)
    client.write_switch.assert_not_awaited()


async def test_hub_get_all_entities(client: MagicMock) -> None:
    """The bulk read is delegated to the client."""
    client.get_all_entities = AsyncMock(return_value={"temp_supply": 45.0})
    hub = QubeHub("1.2.3.4", 502, 1, "qube1")

    assert await hub.async_get_all_entities() == {"temp_supply": 45.0}
    client.get_all_entities.assert_awaited_once()
