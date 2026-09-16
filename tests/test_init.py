"""Tests for the Qube Heat Pump integration setup and unloading."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump import _alarm_group_object_id, _resolve_entry
from custom_components.qube_heatpump.const import CONF_HOST, CONF_NAME, DOMAIN
from custom_components.qube_heatpump.coordinator import STORAGE_KEY_PREFIX
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import async_poll, setup_integration

ALARM_GROUP = "group.qube_alarms_qube_1"


def _entry(host: str, name: str | None = None) -> MockConfigEntry:
    """Return an extra config entry for the multi-device cases."""
    data: dict[str, Any] = {CONF_HOST: host}
    if name is not None:
        data[CONF_NAME] = name
    return MockConfigEntry(
        domain=DOMAIN,
        data=data,
        title=name or "Qube Heat Pump",
        unique_id=f"{DOMAIN}-{host}-502",
    )


@pytest.mark.parametrize(
    ("name", "expected_name", "expected_label"),
    [
        (None, "qube 1", "qube_1"),
        ("my qube", "my qube", "my_qube"),
    ],
    ids=["migrated_default", "configured_name"],
)
async def test_setup_names_the_device_and_derives_its_label(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    name: str | None,
    expected_name: str,
    expected_label: str,
) -> None:
    """An entry without a name gets a numbered one; the label drives entity ids."""
    entry = _entry("1.2.3.4", name)

    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_NAME] == expected_name
    assert entry.title == expected_name
    assert entry.runtime_data.hub.label == expected_label
    assert hass.states.get(f"sensor.{expected_label}_temp_supply") is not None


@pytest.mark.parametrize(
    "connect_result",
    [{"return_value": False}, {"side_effect": OSError("no route")}],
    ids=["refused", "unreachable"],
)
async def test_setup_retries_when_device_unreachable(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    connect_result: dict[str, Any],
) -> None:
    """A failed initial connect leaves the entry in SETUP_RETRY with no entities."""
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(**connect_result)

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.states.async_all()


@pytest.mark.parametrize(
    ("reported", "expected"),
    [("4.10", "4.10"), (None, "unknown")],
    ids=["readable", "unreadable"],
)
async def test_software_version_read_during_setup(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    reported: str | None,
    expected: str,
) -> None:
    """The firmware version read at setup lands on the device; failure is not fatal."""
    mock_qube_client.async_get_software_version = AsyncMock(return_value=reported)

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.version == expected
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, mock_config_entry.entry_id), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.sw_version == expected


async def test_second_entry_is_flagged_as_multi_device(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Only an entry set up while another exists is a multi-device install."""
    await setup_integration(hass, mock_config_entry)
    second = _entry("1.2.3.5")
    await setup_integration(hass, second)

    assert mock_config_entry.runtime_data.multi_device is False
    assert second.runtime_data.multi_device is True


async def test_unload_closes_the_hub_and_stops_polling(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unloading releases the connection, the entities and the poll timer."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get("sensor.qube_1_temp_supply") is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_qube_client.close.assert_awaited_once()
    assert hass.states.get("sensor.qube_1_temp_supply").state == STATE_UNAVAILABLE

    polls = mock_qube_client.get_all_entities.await_count
    await async_poll(hass, freezer)
    assert mock_qube_client.get_all_entities.await_count == polls


async def test_alarm_group_created_and_removed_with_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The alarm group collects this hub's alarm sensors and goes away on unload."""
    await setup_integration(hass, mock_config_entry)

    group = hass.states.get(ALARM_GROUP)
    assert group is not None
    members = group.attributes["entity_id"]
    assert members
    assert all(entity_id.startswith("binary_sensor.qube_1_") for entity_id in members)
    assert "binary_sensor.qube_1_alrm_flw" in members

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ALARM_GROUP) is None


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("qube1", "qube_alarms_qube1"),
        ("qube 1", "qube_alarms_qube_1"),
        ("", "qube_alarms"),
    ],
)
def test_alarm_group_object_id(label: str, expected: str) -> None:
    """The group object_id is the slugified hub label."""
    assert _alarm_group_object_id(label) == expected


async def test_resolve_entry_with_a_single_loaded_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """A matching label or no label resolves; a wrong label must not fall back."""
    entry = _entry("1.2.3.4", "qube1")
    await setup_integration(hass, entry)

    assert _resolve_entry(hass, None, None) is entry
    assert _resolve_entry(hass, None, "qube1") is entry
    assert _resolve_entry(hass, entry.entry_id, None) is entry
    assert _resolve_entry(hass, None, "other") is None
    assert _resolve_entry(hass, "bogus", None) is None


async def test_resolve_entry_with_several_entries(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """With more than one entry only an explicit entry_id or label resolves."""
    first = _entry("1.2.3.4", "qube1")
    second = _entry("1.2.3.5", "qube2")
    await setup_integration(hass, first)
    await setup_integration(hass, second)

    assert _resolve_entry(hass, None, None) is None
    assert _resolve_entry(hass, None, "qube2") is second
    assert _resolve_entry(hass, first.entry_id, None) is first


async def test_resolve_entry_ignores_an_entry_that_is_not_loaded(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An entry that was never set up has no hub to match a label against."""
    mock_config_entry.add_to_hass(hass)

    assert _resolve_entry(hass, None, "qube_1") is None
    assert _resolve_entry(hass, None, None) is None


async def test_options_update_reloads_the_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Changing the options rebuilds the hub and coordinator."""
    await setup_integration(hass, mock_config_entry)
    first_coordinator = mock_config_entry.runtime_data.coordinator

    hass.config_entries.async_update_entry(
        mock_config_entry, options={"dhw_schedule_enabled": False}
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator is not first_coordinator


async def test_remove_entry_deletes_monotonic_store(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Removing the config entry removes its monotonic cache from .storage."""
    key = f"{STORAGE_KEY_PREFIX}_{mock_config_entry.entry_id}"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"energy_total_electric": 1.0},
    }
    await setup_integration(hass, mock_config_entry)

    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert key not in hass_storage
