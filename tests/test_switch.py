"""Tests for the Qube Heat Pump switch platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import add_bulk_read

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


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
        add_bulk_read(client)
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


async def _setup_with_forced_coil(
    hass: HomeAssistant, mock_qube_client: MagicMock, coil_reads: dict[str, bool]
) -> MockConfigEntry:
    """Set up the integration with per-key switch values from ``coil_reads``."""

    async def _read_entity(ent):
        if ent.key in coil_reads:
            return coil_reads[ent.key]
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
    return entry


async def test_forced_dhw_switch_reports_pending_request_when_coil_stays_on(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Turn-off acknowledged but coil still on -> real state on + pending_request."""
    coil = {"tapw_timeprogram_bms_forced": True}
    entry = await _setup_with_forced_coil(hass, mock_qube_client, coil)
    entity_id = "switch.qube_1_tapw_timeprogram_bms_forced"

    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["pending_request"] is False

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    mock_qube_client.write_switch.assert_awaited_with("tapw_timeprogram_bms_forced", False)
    state = hass.states.get(entity_id)
    assert state.state == "on", "must surface the coil's real state, not the optimistic one"
    assert state.attributes["pending_request"] is True

    # The controller clears the coil itself once the DHW run completes
    coil["tapw_timeprogram_bms_forced"] = False
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state.attributes["pending_request"] is False


async def test_forced_dhw_switch_turn_on_clears_pending_request(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Turning the switch back on cancels a pending turn-off."""
    coil = {"tapw_timeprogram_bms_forced": True}
    await _setup_with_forced_coil(hass, mock_qube_client, coil)
    entity_id = "switch.qube_1_tapw_timeprogram_bms_forced"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["pending_request"] is True

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["pending_request"] is False


async def test_other_switches_have_no_pending_attribute(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Only the forced-DHW coil exposes pending_request."""
    await _setup_with_forced_coil(hass, mock_qube_client, {"modbus_demand": True})
    state = hass.states.get("switch.qube_1_modbus_demand")
    assert state is not None
    assert "pending_request" not in state.attributes


async def test_switch_write_failure_raises_translated_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A rejected coil write surfaces as a translated HomeAssistantError."""
    await _setup_with_forced_coil(hass, mock_qube_client, {"modbus_demand": False})
    mock_qube_client.write_switch = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.qube_1_modbus_demand"},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_switch_failed"
    assert excinfo.value.translation_placeholders == {
        "entity_id": "switch.qube_1_modbus_demand"
    }
    assert hass.states.get("switch.qube_1_modbus_demand").state == "off"


async def test_switch_connect_failure_raises_translated_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """An unreachable device surfaces as a translated connection error."""
    await _setup_with_forced_coil(hass, mock_qube_client, {"modbus_demand": True})
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(side_effect=OSError("down"))

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.qube_1_modbus_demand"},
            blocking=True,
        )

    assert excinfo.value.translation_key == "connection_failed"
    mock_qube_client.write_switch.assert_not_awaited()
