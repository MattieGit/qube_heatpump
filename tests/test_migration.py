"""Tests for the v1 -> v2 config entry migration (entry-id keyed identifiers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, CONF_UNIT_ID, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from tests import setup_integration
from tests.conftest import MOCK_ENTRY_ID

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

OLD_PREFIX = "1.2.3.4_1_"


def _v1_entry(host: str = "1.2.3.4", unit: int | None = None) -> MockConfigEntry:
    data = {CONF_HOST: host}
    if unit is not None:
        data[CONF_UNIT_ID] = unit
    return MockConfigEntry(
        domain=DOMAIN,
        data=data,
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-{host}-502",
        entry_id=MOCK_ENTRY_ID,
        version=1,
    )


def _seed_v1_registry(
    hass: HomeAssistant, entry: MockConfigEntry, prefix: str = OLD_PREFIX
) -> tuple[str, str]:
    """Register a device and two entities the way a v1 install left them."""
    area = ar.async_get(hass).async_get_or_create("Utility room")
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, prefix.rstrip("_").replace("_", ":"))},
    )
    # A user-assigned name and area: both must survive the migration
    device_registry.async_update_device(
        device.id, area_id=area.id, name_by_user="Custom name"
    )

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{prefix}temp_supply",
        suggested_object_id="qube_1_temp_supply",
        config_entry=entry,
        device_id=device.id,
    )
    # A user-customised, disabled entity: customisations must survive
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{prefix}modbus_demand",
        suggested_object_id="qube_1_modbus_demand",
        config_entry=entry,
        device_id=device.id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    entity_registry.async_update_entity(
        "sensor.qube_1_temp_supply", name="My supply", icon="mdi:thermometer"
    )
    # Legacy SG Ready rows that older releases created and later cleaned up
    entity_registry.async_get_or_create(
        "switch", DOMAIN, f"{prefix}bms_sgready_a", config_entry=entry
    )
    return device.id, area.id


async def test_v1_entry_migrates_registry_rows_in_place(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Unique ids and the device identifier move to the entry id; nothing else changes."""
    entry = _v1_entry()
    entry.add_to_hass(hass)
    device_id, area_id = _seed_v1_registry(hass, entry)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2

    entity_registry = er.async_get(hass)
    supply = entity_registry.async_get("sensor.qube_1_temp_supply")
    assert supply is not None
    assert supply.unique_id == f"{MOCK_ENTRY_ID}_temp_supply"
    assert supply.name == "My supply"
    assert supply.icon == "mdi:thermometer"
    assert supply.device_id == device_id
    demand = entity_registry.async_get("switch.qube_1_modbus_demand")
    assert demand is not None
    assert demand.unique_id == f"{MOCK_ENTRY_ID}_modbus_demand"
    assert demand.disabled_by is er.RegistryEntryDisabler.USER
    assert not [
        e
        for e in entity_registry.entities.values()
        if e.unique_id.startswith(OLD_PREFIX)
    ]
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{MOCK_ENTRY_ID}_bms_sgready_a"
        )
        is None
    )

    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    assert device is not None
    assert device.identifiers == {(DOMAIN, MOCK_ENTRY_ID)}
    assert device.area_id == area_id
    assert device.name_by_user == "Custom name"
    # No second device was created for the entry
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 1
    # Live entities attach to the migrated device
    assert hass.states.get("sensor.qube_1_temp_supply").state == "45.0"


async def test_migration_uses_the_legacy_unit_id(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A non-default unit id was part of the old prefix; the migration must match it."""
    entry = _v1_entry(unit=3)
    entry.add_to_hass(hass)
    device_id, _ = _seed_v1_registry(hass, entry, prefix="1.2.3.4_3_")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    supply = er.async_get(hass).async_get("sensor.qube_1_temp_supply")
    assert supply.unique_id == f"{MOCK_ENTRY_ID}_temp_supply"
    assert dr.async_get(hass).async_get(device_id).identifiers == {
        (DOMAIN, MOCK_ENTRY_ID)
    }


async def test_migration_is_a_no_op_on_a_current_entry(
    hass: HomeAssistant, mock_qube_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A v2 entry sets up unchanged."""
    assert mock_config_entry.version == 2
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    supply = er.async_get(hass).async_get("sensor.qube_1_temp_supply")
    assert supply.unique_id == f"{MOCK_ENTRY_ID}_temp_supply"


async def test_host_change_keeps_the_device(
    hass: HomeAssistant, mock_qube_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Identifiers no longer embed the host, so changing it keeps device and area."""
    await setup_integration(hass, mock_config_entry)
    device_registry = dr.async_get(hass)
    device = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )[0]
    area = ar.async_get(hass).async_get_or_create("Attic")
    device_registry.async_update_device(device.id, area_id=area.id)

    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_HOST: "192.0.2.99"}
    )
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert [d.id for d in devices] == [device.id]
    assert devices[0].area_id == area.id
    assert hass.states.get("sensor.qube_1_temp_supply").state == "45.0"


@pytest.mark.parametrize("client_values", [{}])
async def test_two_entries_get_distinct_identifiers(
    hass: HomeAssistant, mock_qube_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Two heat pumps never share a device or a unique id."""
    await setup_integration(hass, mock_config_entry)
    second = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8"},
        title="Qube 2",
        unique_id=f"{DOMAIN}-5.6.7.8-502",
        entry_id="01JQUBEHEATPUMP00000000002",
        version=2,
    )
    await setup_integration(hass, second)

    device_registry = dr.async_get(hass)
    first = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    other = dr.async_entries_for_config_entry(device_registry, second.entry_id)
    assert first[0].identifiers == {(DOMAIN, MOCK_ENTRY_ID)}
    assert other[0].identifiers == {(DOMAIN, second.entry_id)}
    uids = [e.unique_id for e in er.async_get(hass).entities.values()]
    assert len(uids) == len(set(uids))
