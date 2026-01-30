"""Tests for the Qube Heat Pump hub."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.qube_heatpump.hub import QubeHub
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
        client.connect = AsyncMock(return_value=False)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        try:
            await hub.async_connect()
        except ConnectionError:
            pass

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
        client.connect = AsyncMock(return_value=True)

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()
        hub.set_unit_id(5)

        assert client.unit == 5


async def test_hub_resolve_ip_with_ip_address(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip with IP address."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "192.168.1.100", 502, "test_entry_id", 1, "qube1")
        await hub.async_resolve_ip()

        assert hub.resolved_ip == "192.168.1.100"


async def test_hub_load_library_entities(hass: HomeAssistant) -> None:
    """Test hub load_library_entities."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
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
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # Set translations
        translations = {
            "entity": {
                "sensor": {
                    "temp_supply": {"name": "Supply Temperature"}
                }
            }
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
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
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

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
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
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "invalid.host", 502, "test_entry_id", 1, "qube1")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(side_effect=OSError)
            await hub.async_resolve_ip()

        assert hub.resolved_ip is None


async def test_hub_resolve_ip_ipv6_mapped(hass: HomeAssistant) -> None:
    """Test hub async_resolve_ip handles IPv6 mapped addresses."""
    import socket

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "qube.local", 502, "test_entry_id", 1, "qube1")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[
                    (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::ffff:192.168.1.50", 0))
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


async def test_hub_decode_and_transform(hass: HomeAssistant) -> None:
    """Test hub _decode_and_transform with different data types."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # Test uint16
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="uint16")
        result = hub._decode_and_transform([1234], ent)
        assert result == 1234

        # Test int16 positive
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="int16")
        result = hub._decode_and_transform([1000], ent)
        assert result == 1000

        # Test int16 negative
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="int16")
        result = hub._decode_and_transform([65535], ent)
        assert result == -1

        # Test with scale
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="uint16", scale=0.1)
        result = hub._decode_and_transform([100], ent)
        assert abs(result - 10.0) < 0.001

        # Test with offset
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="uint16", offset=10.0)
        result = hub._decode_and_transform([100], ent)
        assert result == 110.0

        # Test with scale and offset
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="uint16", scale=0.1, offset=5.0)
        result = hub._decode_and_transform([100], ent)
        assert abs(result - 15.0) < 0.001


async def test_hub_read_value_not_connected(hass: HomeAssistant) -> None:
    """Test hub async_read_value raises when not connected."""
    import pytest
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.load_library_entities()

        # Don't connect, try to read
        if hub.entities:
            with pytest.raises(ConnectionError, match="Client not connected"):
                await hub.async_read_value(hub.entities[0])


async def test_hub_get_friendly_name_none_key(hass: HomeAssistant) -> None:
    """Test hub get_friendly_name with None key."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        hub.set_translations({"entity": {"sensor": {"test": {"name": "Test"}}}})

        # None key should return None
        name = hub.get_friendly_name("sensor", None)
        assert name is None


async def test_hub_get_friendly_name_no_translations(hass: HomeAssistant) -> None:
    """Test hub get_friendly_name with no translations set."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        # Don't set translations

        name = hub.get_friendly_name("sensor", "test")
        assert name is None


async def test_hub_decode_float32(hass: HomeAssistant) -> None:
    """Test hub _decode_and_transform with float32."""
    import struct

    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # Pack float 21.5 as two 16-bit registers
        # Hub uses little endian word order: int_val = (regs[1] << 16) | regs[0]
        # then unpacks as big endian float
        packed = struct.pack(">f", 21.5)
        int_val = struct.unpack(">I", packed)[0]
        reg0 = int_val & 0xFFFF  # Low word
        reg1 = (int_val >> 16) & 0xFFFF  # High word

        ent = EntityDef(platform="sensor", name="test", address=0, data_type="float32")
        result = hub._decode_and_transform([reg0, reg1], ent)
        assert abs(result - 21.5) < 0.001


async def test_hub_decode_uint32(hass: HomeAssistant) -> None:
    """Test hub _decode_and_transform with uint32."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # uint32: 70000 = 0x00011170
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="uint32")
        # Low word, high word in little endian order
        result = hub._decode_and_transform([0x1170, 0x0001], ent)
        assert result == 70000


async def test_hub_decode_int32(hass: HomeAssistant) -> None:
    """Test hub _decode_and_transform with int32."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")

        # int32 positive
        ent = EntityDef(platform="sensor", name="test", address=0, data_type="int32")
        result = hub._decode_and_transform([0x1170, 0x0001], ent)
        assert result == 70000

        # int32 negative (-1 = 0xFFFFFFFF)
        result = hub._decode_and_transform([0xFFFF, 0xFFFF], ent)
        assert result == -1


async def test_hub_read_by_address_binary_sensor_discrete(hass: HomeAssistant) -> None:
    """Test hub _read_by_address for binary sensor with discrete input."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_discrete_inputs = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[True])
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="binary_sensor",
            name="test",
            address=100,
            input_type="discrete_input",
        )
        result = await hub._read_by_address(ent)
        assert result is True


async def test_hub_read_by_address_binary_sensor_coil(hass: HomeAssistant) -> None:
    """Test hub _read_by_address for binary sensor with coil input."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="binary_sensor",
            name="test",
            address=100,
            input_type="coil",
        )
        result = await hub._read_by_address(ent)
        assert result is False


async def test_hub_read_by_address_switch(hass: HomeAssistant) -> None:
    """Test hub _read_by_address for switch."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[True])
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            write_type="coil",
        )
        result = await hub._read_by_address(ent)
        assert result is True


async def test_hub_read_sensor_registers_input(hass: HomeAssistant) -> None:
    """Test hub _read_sensor_registers with input registers."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_input_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[1234])
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            input_type="input",
            data_type="uint16",
        )
        result = await hub._read_sensor_registers(ent)
        assert result == 1234


async def test_hub_read_sensor_registers_holding(hass: HomeAssistant) -> None:
    """Test hub _read_sensor_registers with holding registers."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[5678])
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            input_type="holding",
            data_type="uint16",
        )
        result = await hub._read_sensor_registers(ent)
        assert result == 5678


async def test_hub_read_sensor_registers_error(hass: HomeAssistant) -> None:
    """Test hub _read_sensor_registers handles error response."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: True)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            input_type="holding",
            data_type="uint16",
        )
        result = await hub._read_sensor_registers(ent)
        assert result is None


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
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.read_binary_sensor = AsyncMock(return_value=True)
        client.read_switch = AsyncMock(return_value=False)
        client.read_sensor = AsyncMock(return_value=42.0)
        client._client = MagicMock()

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


async def test_hub_write_switch_coil_fallback(hass: HomeAssistant) -> None:
    """Test hub async_write_switch with coil fallback."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        # write_switch returns None to trigger fallback
        client.write_switch = AsyncMock(return_value=None)
        client._client = MagicMock()
        client._client.write_coil = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        # Entity without library entity to trigger fallback
        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            write_type="coil",
        )
        ent._library_entity = None
        ent.unique_id = None

        await hub.async_write_switch(ent, True)
        client._client.write_coil.assert_called()


async def test_hub_write_switch_coil_error(hass: HomeAssistant) -> None:
    """Test hub async_write_switch handles coil write error."""
    import pytest
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.write_switch = AsyncMock(return_value=None)
        client._client = MagicMock()
        client._client.write_coil = AsyncMock(
            return_value=MagicMock(isError=lambda: True)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        ent = EntityDef(
            platform="switch",
            name="test",
            address=100,
            write_type="coil",
        )
        ent._library_entity = None
        ent.unique_id = None

        with pytest.raises(ConnectionError, match="Failed to write coil"):
            await hub.async_write_switch(ent, True)


async def test_hub_write_setpoint_fallback(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint with register fallback."""
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.write_setpoint = AsyncMock(return_value=False)
        client._client = MagicMock()
        client._client.write_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        # Entity without unique_id to trigger fallback
        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            data_type="float32",
        )
        ent._library_entity = None

        await hub.async_write_setpoint(ent, 21.5)
        client._client.write_registers.assert_called()


async def test_hub_write_setpoint_error(hass: HomeAssistant) -> None:
    """Test hub async_write_setpoint handles error."""
    import pytest
    from custom_components.qube_heatpump.hub import EntityDef

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.write_setpoint = AsyncMock(return_value=False)
        client._client = MagicMock()

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        # Entity with unique_id that fails
        ent = EntityDef(
            platform="sensor",
            name="test",
            address=100,
            unique_id="test_setpoint",
        )

        with pytest.raises(ConnectionError, match="Failed to write setpoint"):
            await hub.async_write_setpoint(ent, 21.5)


async def test_hub_write_register_int16_negative(hass: HomeAssistant) -> None:
    """Test hub async_write_register with negative int16."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: False)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        await hub.async_write_register(100, -10, "int16")
        client._client.write_register.assert_called()


async def test_hub_write_register_error(hass: HomeAssistant) -> None:
    """Test hub async_write_register handles error."""
    import pytest

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client._client = MagicMock()
        client._client.write_register = AsyncMock(
            return_value=MagicMock(isError=lambda: True)
        )

        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        await hub.async_connect()

        with pytest.raises(ConnectionError, match="Failed to write register"):
            await hub.async_write_register(100, 42, "uint16")


async def test_hub_write_register_not_connected(hass: HomeAssistant) -> None:
    """Test hub async_write_register raises when not connected."""
    import pytest

    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ):
        hub = QubeHub(hass, "1.2.3.4", 502, "test_entry_id", 1, "qube1")
        # Don't connect

        with pytest.raises(ConnectionError, match="Client not connected"):
            await hub.async_write_register(100, 42, "uint16")
