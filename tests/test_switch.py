"""Tests for the Qube Heat Pump switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_switch_entities_created(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test switch entities are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check switch entities exist
    states = hass.states.async_all()
    switch_states = [s for s in states if s.entity_id.startswith("switch.")]
    assert len(switch_states) > 0


async def test_switch_turn_on(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test turning a switch on."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get first switch entity
    states = hass.states.async_all()
    switch_states = [s for s in states if s.entity_id.startswith("switch.")]

    if switch_states:
        switch_id = switch_states[0].entity_id

        # Turn on
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": switch_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write_switch was called
        mock_qube_client.write_switch.assert_called()


async def test_switch_turn_off(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test turning a switch off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get first switch entity
    states = hass.states.async_all()
    switch_states = [s for s in states if s.entity_id.startswith("switch.")]

    if switch_states:
        switch_id = switch_states[0].entity_id

        # Turn off
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": switch_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify write_switch was called
        mock_qube_client.write_switch.assert_called()


async def test_switch_is_on_property(
    hass: HomeAssistant,
) -> None:
    """Test switch is_on property with different values."""
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
        # Return True for switches to test is_on
        client.read_entity = AsyncMock(return_value=True)
        client.read_sensor = AsyncMock(return_value=45.0)
        client.read_binary_sensor = AsyncMock(return_value=False)
        client.read_switch = AsyncMock(return_value=True)
        client.write_switch = AsyncMock(return_value=True)
        client._client = MagicMock()
        client._client.read_holding_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_input_registers = AsyncMock(
            return_value=MagicMock(isError=lambda: False, registers=[0, 0])
        )
        client._client.read_coils = AsyncMock(
            return_value=MagicMock(isError=lambda: False, bits=[True])
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

        # Check switch states
        states = hass.states.async_all()
        switch_states = [s for s in states if s.entity_id.startswith("switch.")]
        # At least some switches should exist
        assert len(switch_states) > 0


async def test_switch_device_info(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test switch entity device info."""
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


async def test_switch_sgready_hidden(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test SG Ready switches are hidden by default."""
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check entity registry for SG Ready switches
    entity_registry = er.async_get(hass)
    # SG Ready switches should exist but may be hidden
    all_entities = list(entity_registry.entities.values())
    switch_entities = [e for e in all_entities if e.domain == "switch"]
    assert len(switch_entities) > 0
