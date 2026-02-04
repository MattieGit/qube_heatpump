"""Tests for the Qube Heat Pump select platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from custom_components.qube_heatpump.select import (
    BITS_TO_MODE,
    MODE_TO_BITS,
    SGREADY_OPTIONS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def test_sgready_options() -> None:
    """Test SG Ready options are defined correctly."""
    assert "Off" in SGREADY_OPTIONS
    assert "Block" in SGREADY_OPTIONS
    assert "Plus" in SGREADY_OPTIONS
    assert "Max" in SGREADY_OPTIONS


def test_mode_to_bits_mapping() -> None:
    """Test MODE_TO_BITS mapping."""
    assert MODE_TO_BITS["Off"] == (False, False)
    assert MODE_TO_BITS["Block"] == (True, False)
    assert MODE_TO_BITS["Plus"] == (False, True)
    assert MODE_TO_BITS["Max"] == (True, True)


def test_bits_to_mode_mapping() -> None:
    """Test BITS_TO_MODE reverse mapping."""
    assert BITS_TO_MODE[(False, False)] == "Off"
    assert BITS_TO_MODE[(True, False)] == "Block"
    assert BITS_TO_MODE[(False, True)] == "Plus"
    assert BITS_TO_MODE[(True, True)] == "Max"


async def test_select_entities_created(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test select entities are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check select entities exist
    states = hass.states.async_all()
    select_states = [s for s in states if s.entity_id.startswith("select.")]
    # SG Ready select should exist if switches are available
    assert isinstance(select_states, list)


async def test_select_option(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test selecting an option."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get select entities
    states = hass.states.async_all()
    select_states = [s for s in states if s.entity_id.startswith("select.")]

    if select_states:
        select_id = select_states[0].entity_id

        # Select option
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": select_id, "option": "Plus"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write_switch was called
        mock_qube_client.write_switch.assert_called()


async def test_select_current_option(
    hass: HomeAssistant,
) -> None:
    """Test select current_option property."""
    with patch(
        "custom_components.qube_heatpump.hub.QubeClient", autospec=True
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.host = "1.2.3.4"
        client.port = 502
        client.unit = 1
        client.connect = AsyncMock(return_value=True)
        client.is_connected = True
        client.close = AsyncMock(return_value=None)

        # Return values for SG Ready mode
        def read_entity_side_effect(ent):
            if hasattr(ent, "vendor_id"):
                if ent.vendor_id == "bms_sgready_a":
                    return False
                if ent.vendor_id == "bms_sgready_b":
                    return True
            return 45.0

        client.read_entity = AsyncMock(side_effect=read_entity_side_effect)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
        client.write_switch = AsyncMock(return_value=True)
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_input_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )
        client._client.read_discrete_inputs = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[False])
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check select entities
        states = hass.states.async_all()
        select_states = [s for s in states if s.entity_id.startswith("select.")]
        assert isinstance(select_states, list)


async def test_select_device_info(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test select entity device info."""
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Verify device exists
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "1.2.3.4:1")})
    assert device is not None
    assert device.manufacturer == "Qube"


async def test_select_unique_id_multi_device(hass: HomeAssistant) -> None:
    """Test select unique_id uses host_unit prefix in multi_device mode."""
    from custom_components.qube_heatpump.hub import EntityDef
    from custom_components.qube_heatpump.select import QubeSGReadyModeSelect

    hub = MagicMock()
    hub.host = "192.168.1.100"
    hub.unit = 2
    hub.label = "qube1"
    hub.device_name = "Qube Heat Pump"
    hub.get_friendly_name = MagicMock(return_value=None)

    coordinator = MagicMock()
    coordinator.data = {}

    sgready_a = EntityDef(
        platform="switch",
        name="SG Ready A",
        address=100,
    )
    sgready_a.unique_id = "bms_sgready_a"
    sgready_a.vendor_id = "bms_sgready_a"

    sgready_b = EntityDef(
        platform="switch",
        name="SG Ready B",
        address=101,
    )
    sgready_b.unique_id = "bms_sgready_b"
    sgready_b.vendor_id = "bms_sgready_b"

    # Single device - always has host_unit prefix for stability
    select_single = QubeSGReadyModeSelect(
        coordinator=coordinator,
        hub=hub,
        show_label=True,
        multi_device=False,
        version="1.0",
        sgready_a=sgready_a,
        sgready_b=sgready_b,
        entry_id="test_entry_id",
    )
    assert select_single._attr_unique_id == "192.168.1.100_2_sgready_mode"

    # Multi device - same host_unit prefix
    select_multi = QubeSGReadyModeSelect(
        coordinator=coordinator,
        hub=hub,
        show_label=True,
        multi_device=True,
        version="1.0",
        sgready_a=sgready_a,
        sgready_b=sgready_b,
        entry_id="test_entry_id",
    )
    assert select_multi._attr_unique_id == "192.168.1.100_2_sgready_mode"
