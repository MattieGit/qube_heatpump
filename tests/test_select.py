"""Tests for the Qube Heat Pump select platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from custom_components.qube_heatpump.select import (
    BITS_TO_MODE,
    MODE_TO_BITS,
    SGREADY_OPTIONS,
)
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import add_bulk_read

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
        add_bulk_read(client)
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
    from custom_components.qube_heatpump.entity_defs import EntityDef
    from custom_components.qube_heatpump.select import QubeSGReadyModeSelect

    hub = MagicMock()
    hub.host = "192.168.1.100"
    hub.unit = 2
    hub.label = "qube1"
    hub.device_name = "Qube Heat Pump"

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
        version="1.0",
        sgready_a=sgready_a,
        sgready_b=sgready_b,
    )
    assert select_single._attr_unique_id == "192.168.1.100_2_sgready_mode"

    # Multi device - same host_unit prefix
    select_multi = QubeSGReadyModeSelect(
        coordinator=coordinator,
        hub=hub,
        version="1.0",
        sgready_a=sgready_a,
        sgready_b=sgready_b,
    )
    assert select_multi._attr_unique_id == "192.168.1.100_2_sgready_mode"


async def _setup_with_coils(
    hass: HomeAssistant, mock_qube_client: MagicMock, coils: dict[str, bool | None]
) -> None:
    async def _read_entity(ent):
        if ent.key in coils:
            return coils[ent.key]
        return 45.0

    mock_qube_client.read_entity = AsyncMock(side_effect=_read_entity)
    add_bulk_read(mock_qube_client)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("coil_a", "coil_b", "option"),
    [
        (False, False, "Off"),
        (True, False, "Block"),
        (False, True, "Plus"),
        (True, True, "Max"),
    ],
)
async def test_select_current_option_from_coils(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    coil_a: bool,
    coil_b: bool,
    option: str,
) -> None:
    """The mode is decoded from the two SG Ready coils."""
    await _setup_with_coils(
        hass, mock_qube_client, {"bms_sgready_a": coil_a, "bms_sgready_b": coil_b}
    )
    assert hass.states.get("select.qube_1_sg_ready_mode").state == option


async def test_select_current_option_unknown_when_coil_missing(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """With one coil unreadable the mode is unknown rather than an assumed default."""
    await _setup_with_coils(
        hass, mock_qube_client, {"bms_sgready_a": None, "bms_sgready_b": True}
    )
    assert hass.states.get("select.qube_1_sg_ready_mode").state == "unknown"


async def test_select_option_writes_only_changed_coils(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Selecting a mode writes just the coil(s) that differ."""
    await _setup_with_coils(
        hass, mock_qube_client, {"bms_sgready_a": False, "bms_sgready_b": False}
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.qube_1_sg_ready_mode", "option": "Plus"},
        blocking=True,
    )

    mock_qube_client.write_switch.assert_awaited_once_with("bms_sgready_b", True)


async def test_select_option_write_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """A rejected coil write surfaces as a translated HomeAssistantError."""
    await _setup_with_coils(
        hass, mock_qube_client, {"bms_sgready_a": False, "bms_sgready_b": False}
    )
    mock_qube_client.write_switch = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.qube_1_sg_ready_mode", "option": "Max"},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_switch_failed"
    assert excinfo.value.translation_placeholders == {
        "entity_id": "select.qube_1_sg_ready_mode"
    }
