"""Tests for the Qube Heat Pump hub."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.qube_heatpump.hub import QubeHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_hub_properties(hass: HomeAssistant) -> None:
    """Test hub properties."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        assert hub.host == "1.2.3.4"
        assert hub.port == 502
        assert hub.unit == 1
        assert hub.label == "qube1"
        assert hub.entry_id == "test_entry_id"
        assert hub.resolved_ip is None
        assert hub.err_connect == 0


async def test_hub_default_label(hass: HomeAssistant) -> None:
    """Test hub with default label."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, None)

        assert hub.label == "qube1"


async def test_hub_connect_success(hass: HomeAssistant) -> None:
    """Test successful connection."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        client.connect.assert_called_once()
        assert hub.err_connect == 0


async def test_hub_connect_failure_increments_error(hass: HomeAssistant) -> None:
    """Test connection failure increments error counter."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=False)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        with contextlib.suppress(ConnectionError):
            await hub.async_connect()

        assert hub.err_connect == 1


async def test_hub_close(hass: HomeAssistant) -> None:
    """Test hub close."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.close = AsyncMock(return_value=None)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()
        await hub.async_close()

        client.close.assert_called_once()


async def test_hub_set_unit_id(hass: HomeAssistant) -> None:
    """Test hub set_unit_id."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()
        hub.set_unit_id(5)

        assert client.unit == 5


async def test_hub_resolve_ip_with_ip_address(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip with IP address."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "192.168.1.100", 502, "test_entry_id", 1, "qube1")
        await hub.async_resolve_ip()

        assert hub.resolved_ip == "192.168.1.100"


async def test_hub_load_library_entities(hass: HomeAssistant) -> None:
    """Test hub load_library_entities."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()

        # Should have loaded entities from the library
        assert len(hub.entities) > 0


async def test_hub_read_value(hass: HomeAssistant) -> None:
    """Test hub async_read_value."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.read_entity = AsyncMock(return_value=45.0)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()
        await hub.async_connect()

        # Read a value from the first entity
        if hub.entities:
            value = await hub.async_read_value(hub.entities[0])
            assert value == 45.0


async def test_hub_translations(hass: HomeAssistant) -> None:
    """Test hub set and get translations."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # Set translations
        translations = {
            "entity": {"sensor": {"temp_supply": {"name": "Supply Temperature"}}}
        }
        hub.set_translations(translations)

        # Get friendly name
        name = hub.get_friendly_name("sensor", "temp_supply")
        assert name == "Supply Temperature"

        # Get friendly name for non-existent key
        name = hub.get_friendly_name("sensor", "nonexistent")
        assert name is None


async def test_hub_inc_read_error(hass: HomeAssistant) -> None:
    """Test hub inc_read_error and err_read."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        assert hub.err_read == 0
        hub.inc_read_error()
        assert hub.err_read == 1
        hub.inc_read_error()
        assert hub.err_read == 2


async def test_hub_connect_exception(hass: HomeAssistant) -> None:
    """Test connection exception increments error counter."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(side_effect=OSError("Network error"))

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        try:
            await hub.async_connect()
        except ConnectionError as e:
            assert "Network error" in str(e)

        assert hub.err_connect == 1


async def test_hub_resolve_ip_dns(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip with DNS resolution."""
    import socket

    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "qube.local", 502, "test_entry_id", 1, "qube1")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))
                ]
            )
            await hub.async_resolve_ip()

        assert hub.resolved_ip == "192.168.1.50"


async def test_hub_resolve_ip_dns_failure(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip handles DNS failure."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "invalid.host", 502, "test_entry_id", 1, "qube1")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(side_effect=OSError)
            await hub.async_resolve_ip()

        assert hub.resolved_ip is None


async def test_hub_resolve_ip_ipv6_mapped(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip handles IPv6 mapped addresses."""
    import socket

    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "qube.local", 502, "test_entry_id", 1, "qube1")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[
                    (
                        socket.AF_INET6,
                        socket.SOCK_STREAM,
                        0,
                        "",
                        ("::ffff:192.168.1.50", 0),
                    )
                ]
            )
            await hub.async_resolve_ip()

        assert hub.resolved_ip == "192.168.1.50"


async def test_hub_write_switch(hass: HomeAssistant) -> None:
    """Test hub async_write_switch."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_switch = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()
        await hub.async_connect()

        # Find a switch entity
        switch_entities = [e for e in hub.entities if e.platform == "switch"]
        if switch_entities:
            await hub.async_write_switch(switch_entities[0], True)
            client.write_switch.assert_called()


async def test_hub_write_setpoint(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_setpoint = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()
        await hub.async_connect()

        # Find a sensor entity (setpoints are typically sensors)
        sensor_entities = [e for e in hub.entities if e.platform == "sensor"]
        if sensor_entities:
            await hub.async_write_setpoint(sensor_entities[0], 21.5)
            client.write_setpoint.assert_called()


async def test_hub_read_value_not_connected(hass: HomeAssistant) -> None:
    """Test hub async_read_value raises when not connected."""
    import pytest

    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()

        # Don't connect, try to read
        if hub.entities:
            with pytest.raises(ConnectionError, match="Client not connected"):
                await hub.async_read_value(hub.entities[0])


async def test_hub_get_friendly_name_none_key(hass: HomeAssistant) -> None:
    """Test hub get_friendly_name with None key."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.set_translations({"entity": {"sensor": {"test": {"name": "Test"}}}})

        # None key should return None
        name = hub.get_friendly_name("sensor", None)
        assert name is None


async def test_hub_get_friendly_name_no_translations(hass: HomeAssistant) -> None:
    """Test hub get_friendly_name with no translations set."""
    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        # Don't set translations

        name = hub.get_friendly_name("sensor", "test")
        assert name is None


async def test_hub_read_value_fallback_unique_id(hass: HomeAssistant) -> None:
    """Test hub async_read_value with unique_id fallback."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.read_binary_sensor = AsyncMock(return_value=True)
        client.read_switch = AsyncMock(return_value=False)
        client.read_sensor = AsyncMock(return_value=42.0)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        # Binary sensor with unique_id (no library entity)
        ent = EntityDef(
            platform="binary_sensor",
            name="test",
            address=100,
            unique_id="test_binary",
        )
        ent._library_entity = None
        result = await hub.async_read_value(ent)
        assert result is True

        # Switch with unique_id
        ent = EntityDef(
            platform="switch",
            name="test",
            address=101,
            unique_id="test_switch",
        )
        ent._library_entity = None
        result = await hub.async_read_value(ent)
        assert result is False

        # Sensor with unique_id
        ent = EntityDef(
            platform="sensor",
            name="test",
            address=102,
            unique_id="test_sensor",
        )
        ent._library_entity = None
        result = await hub.async_read_value(ent)
        assert result == 42.0


async def test_hub_write_switch_success(hass: HomeAssistant) -> None:
    """Test hub async_write_switch with library method."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_switch = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            unique_id="test_switch",
            write_type="coil",
        )

        await hub.async_write_switch(ent, True)
        client.write_switch.assert_called_once_with("test_switch", True)


async def test_hub_write_switch_failure(hass: HomeAssistant) -> None:
    """Test hub async_write_switch handles failure."""
    import pytest

    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_switch = AsyncMock(return_value=False)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            unique_id="test_switch",
            write_type="coil",
        )

        with pytest.raises(ConnectionError, match="Failed to write switch"):
            await hub.async_write_switch(ent, True)


async def test_hub_write_switch_no_unique_id(hass: HomeAssistant) -> None:
    """Test hub async_write_switch raises with no unique_id."""
    import pytest

    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            unique_id=None,
        )

        with pytest.raises(ConnectionError, match="No unique_id for switch"):
            await hub.async_write_switch(ent, True)


async def test_hub_write_setpoint_success(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint with library method."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_setpoint = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            unique_id="test_setpoint",
        )

        await hub.async_write_setpoint(ent, 21.5)
        client.write_setpoint.assert_called_once_with("test_setpoint", 21.5)


async def test_hub_write_setpoint_failure(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint handles failure."""
    import pytest

    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_setpoint = AsyncMock(return_value=False)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            unique_id="test_setpoint",
        )

        with pytest.raises(ConnectionError, match="Failed to write setpoint"):
            await hub.async_write_setpoint(ent, 21.5)


async def test_hub_write_setpoint_no_unique_id(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint raises with no unique_id."""
    import pytest

    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            unique_id=None,
        )

        with pytest.raises(ConnectionError, match="No unique_id for setpoint"):
            await hub.async_write_setpoint(ent, 21.5)


async def test_hub_write_register_with_entity(hass: HomeAssistant) -> None:
    """Test hub async_write_register with matching entity."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.write_setpoint = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()
        await hub.async_connect()

        # Find a writable sensor entity
        writable_sensors = [
            e for e in hub.entities if e.writable and e.platform == "sensor"
        ]
        if writable_sensors:
            ent = writable_sensors[0]
            await hub.async_write_register(ent.address, 21.5)
            client.write_setpoint.assert_called()


async def test_hub_write_register_no_matching_entity(hass: HomeAssistant) -> None:
    """Test hub async_write_register with no matching entity."""
    import pytest

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()
        await hub.async_connect()

        # Use an address that doesn't match any writable entity
        with pytest.raises(ConnectionError, match="No writable entity found"):
            await hub.async_write_register(99999, 42)


async def test_hub_write_register_not_connected(hass: HomeAssistant) -> None:
    """Test hub async_write_register raises when not connected."""
    import pytest

    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        # Don't connect

        with pytest.raises(ConnectionError, match="Client not connected"):
            await hub.async_write_register(100, 42, "uint16")


async def test_hub_get_all_entities(hass: HomeAssistant) -> None:
    """Test hub async_get_all_entities."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.is_connected = False
        client.connect = AsyncMock(return_value=True)
        client.get_all_entities = AsyncMock(return_value={"temp_supply": 45.0})

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        result = await hub.async_get_all_entities()
        assert result == {"temp_supply": 45.0}
        client.get_all_entities.assert_called_once()


async def test_hub_get_all_entities_not_connected(hass: HomeAssistant) -> None:
    """Test hub async_get_all_entities raises when not connected."""
    import pytest

    with patch("custom_components.qube_heatpump.hub.QubeClient", autospec=True):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        # Don't connect

        with pytest.raises(ConnectionError, match="Client not connected"):
            await hub.async_get_all_entities()
