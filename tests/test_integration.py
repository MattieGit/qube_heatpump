"""End-to-end setup and teardown of the Qube Heat Pump integration."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import setup_integration

ALARM_GROUP = "group.qube_alarms_qube_1"


async def test_full_lifecycle(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Setting the entry up registers the device, entities and alarm group.

    Unloading it must release everything: every entity goes unavailable, the
    runtime data is dropped, the alarm group is removed and the connection to
    the controller is closed.
    """
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, mock_config_entry.entry_id), mock_config_entry.entry_id
    )
    assert device is not None

    entity_ids = {
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.split(".", 1)[1].startswith("qube_1_")
    }
    # One entity per platform, proving every platform was forwarded
    assert {entity_id.split(".", 1)[0] for entity_id in entity_ids} == {
        "binary_sensor",
        "button",
        "number",
        "select",
        "sensor",
        "switch",
    }
    assert hass.states.get("sensor.qube_1_temp_supply").state == "45.0"
    # The alarm group lists the alarm binary sensors that were created
    alarm_group = hass.states.get(ALARM_GROUP)
    assert alarm_group is not None
    assert set(alarm_group.attributes["entity_id"]) <= entity_ids

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(mock_config_entry, "runtime_data")
    mock_qube_client.close.assert_awaited_once()
    assert hass.states.get(ALARM_GROUP) is None
    # The entities are gone; what is left are the registry's restored
    # placeholders, so nothing keeps reporting stale readings.
    assert {hass.states.get(entity_id).state for entity_id in entity_ids} == {
        "unavailable"
    }
