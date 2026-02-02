"""Tests for the Qube Heat Pump integration setup and unloading."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_ENTITY_PREFIX,
    CONF_HOST,
    DEFAULT_ENTITY_PREFIX,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_async_setup_entry_registers_integration(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test setup entry registers the integration and creates entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert config entry state via ConfigEntry.state attribute
    assert entry.state is ConfigEntryState.LOADED

    # Assert entity state via core state machine
    states = hass.states.async_all()
    sensor_states = [s for s in states if s.entity_id.startswith("sensor.")]
    assert len(sensor_states) > 0


async def test_async_unload_entry_cleans_up(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Ensure unload removes stored data and closes the hub."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Unload via config entries interface
    result = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert result is True
    # Assert config entry state after unload
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_async_setup_entry_multi_device(
    hass: HomeAssistant,
) -> None:
    """Test multi-device setup marks entries appropriately."""
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
        client.read_entity = AsyncMock(return_value=45.0)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=False)
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

        # First entry - add and setup
        entry1 = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube 1",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry1.add_to_hass(hass)
        await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

        # Second entry - add and setup after first is done
        entry2 = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.5"},
            title="Qube 2",
            unique_id=f"{DOMAIN}-1.2.3.5-502",
        )
        entry2.add_to_hass(hass)
        await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

        assert entry1.state is ConfigEntryState.LOADED
        assert entry2.state is ConfigEntryState.LOADED

        # In multi-device setup, both entries should have multi_device=True
        assert entry1.runtime_data.multi_device is True
        assert entry2.runtime_data.multi_device is True


async def test_async_setup_entry_label_from_options(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test label is taken from entity_prefix option."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump (my_qube)",
        options={CONF_ENTITY_PREFIX: "my_qube"},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.label == "my_qube"


async def test_async_setup_entry_label_default(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test label uses default when no option set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="My Qube Device",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.label == DEFAULT_ENTITY_PREFIX


def test_suggest_object_id_none_base() -> None:
    """Test _suggest_object_id returns None when base is missing."""
    from custom_components.qube_heatpump import _suggest_object_id
    from custom_components.qube_heatpump.hub import EntityDef

    ent = EntityDef(platform="sensor", name="Test", address=100)
    ent.vendor_id = None
    ent.unique_id = None

    result = _suggest_object_id(ent, "qube1")
    assert result is None


def test_suggest_object_id_unitstatus() -> None:
    """Test _suggest_object_id handles unitstatus special case."""
    from custom_components.qube_heatpump import _suggest_object_id
    from custom_components.qube_heatpump.hub import EntityDef

    ent = EntityDef(platform="sensor", name="Test", address=100, vendor_id="UnitStatus")

    result = _suggest_object_id(ent, None)
    assert result == "qube_status_heatpump"


def test_is_alarm_entity() -> None:
    """Test _is_alarm_entity detection."""
    from custom_components.qube_heatpump import _is_alarm_entity
    from custom_components.qube_heatpump.hub import EntityDef

    # Alarm by name
    ent1 = EntityDef(platform="binary_sensor", name="Alarm Test", address=100)
    assert _is_alarm_entity(ent1) is True

    # Alarm by vendor_id starting with "al"
    ent2 = EntityDef(
        platform="binary_sensor", name="Test", address=101, vendor_id="alrm_test"
    )
    assert _is_alarm_entity(ent2) is True

    # Not an alarm - wrong platform
    ent3 = EntityDef(platform="sensor", name="Alarm Test", address=102)
    assert _is_alarm_entity(ent3) is False

    # Not an alarm - no alarm indicator
    ent4 = EntityDef(platform="binary_sensor", name="Test", address=103)
    assert _is_alarm_entity(ent4) is False


def test_alarm_group_object_id() -> None:
    """Test _alarm_group_object_id generation."""
    from custom_components.qube_heatpump import _alarm_group_object_id

    # Single device
    result = _alarm_group_object_id(None, False)
    assert result == "qube_alarm_sensors"

    # Multi-device with label
    result = _alarm_group_object_id("qube1", True)
    assert result == "qube_alarm_sensors_qube1"


def test_derive_label_from_title() -> None:
    """Test derive_label_from_title function."""
    from custom_components.qube_heatpump.helpers import derive_label_from_title

    # With parentheses
    assert derive_label_from_title("Qube Heat Pump (qube.local)") == "qube_local"
    assert derive_label_from_title("Qube Heat Pump (192.168.1.50)") == "192_168_1_50"

    # Without parentheses - fallback to slug
    assert derive_label_from_title("My Heat Pump") == "my_heat_pump"


async def test_resolve_entry_by_label(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test _resolve_entry resolves entry by label."""
    from custom_components.qube_heatpump import _resolve_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump (testlabel)",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        options={CONF_ENTITY_PREFIX: "testlabel"},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Resolve by label
    result = _resolve_entry(hass, None, "testlabel")
    assert result is not None
    assert result.entry_id == entry.entry_id


async def test_resolve_entry_no_match(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test _resolve_entry returns None when no match."""
    from custom_components.qube_heatpump import _resolve_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump (testlabel)",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        options={CONF_ENTITY_PREFIX: "testlabel"},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Add a second entry so auto-resolve fails
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.5"},
        title="Qube Heat Pump (other)",
        unique_id=f"{DOMAIN}-1.2.3.5-502",
        options={CONF_ENTITY_PREFIX: "other"},
    )
    entry2.add_to_hass(hass)
    await hass.config_entries.async_setup(entry2.entry_id)
    await hass.async_block_till_done()

    # Try to resolve with non-matching label
    result = _resolve_entry(hass, None, "nonexistent")
    assert result is None


async def test_resolve_entry_by_hub_label(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test _resolve_entry resolves entry by hub.label attribute."""
    from custom_components.qube_heatpump import _resolve_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump (qube1)",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        options={CONF_ENTITY_PREFIX: "qube1"},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The hub should have label set from options
    result = _resolve_entry(hass, None, "qube1")
    assert result is not None
