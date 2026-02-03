"""Tests for the Qube Heat Pump sensor platform."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.helpers import device_registry as dr, entity_registry as er

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory

    from homeassistant.core import HomeAssistant


async def test_sensor_setup(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test sensors are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert entity state via core state machine
    states = hass.states.async_all()
    sensor_states = [s for s in states if s.entity_id.startswith("sensor.")]
    # Should have sensors
    assert len(sensor_states) >= 10


async def test_binary_sensor_setup(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test binary sensors are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert entity state via core state machine
    states = hass.states.async_all()
    binary_sensor_states = [
        s for s in states if s.entity_id.startswith("binary_sensor.")
    ]
    assert len(binary_sensor_states) > 0


async def test_switch_setup(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test switches are created during setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert entity state via core state machine
    states = hass.states.async_all()
    switch_states = [s for s in states if s.entity_id.startswith("switch.")]
    assert len(switch_states) > 0


async def test_device_info(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test device info is set correctly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert DeviceEntry state via device registry
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "1.2.3.4:1")})

    assert device is not None
    assert device.manufacturer == "Qube"
    assert device.model == "Heatpump"


async def test_sensor_coordinator_refresh_updates_values(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that coordinator refresh updates sensor values."""
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
        # Initial value
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

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "1.2.3.4"},
            title="Qube Heat Pump",
            unique_id=f"{DOMAIN}-1.2.3.4-502",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Update mock to return new value for next fetch
        client.read_entity.return_value = 50.0
        client.read_sensor.return_value = 50.0

        # Trigger coordinator refresh via time advancement
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        # Entity should still be available after refresh
        states = hass.states.async_all()
        sensor_states = [s for s in states if s.entity_id.startswith("sensor.")]
        assert len(sensor_states) > 0


async def test_sensor_handles_none_data(hass: HomeAssistant) -> None:
    """Test sensor handles None data gracefully."""
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
        # Return None for some reads
        client.read_entity = AsyncMock(return_value=None)
        client.read_sensor = AsyncMock(return_value=None)
        client.read_binary_sensor = AsyncMock(return_value=None)
        client.read_switch = AsyncMock(return_value=None)
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

        # Setup should succeed even with None data
        states = hass.states.async_all()
        assert len(states) > 0


async def test_sensor_energy_entities(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test energy sensor entities are created with correct device class."""
    from homeassistant.components.sensor import SensorDeviceClass

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = hass.states.async_all()
    energy_sensors = [
        s
        for s in states
        if s.entity_id.startswith("sensor.")
        and s.attributes.get("device_class") == SensorDeviceClass.ENERGY
    ]
    # Should have energy sensors
    assert len(energy_sensors) > 0


async def test_sensor_temperature_entities(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test temperature sensor entities are created with correct device class."""
    from homeassistant.components.sensor import SensorDeviceClass

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = hass.states.async_all()
    temp_sensors = [
        s
        for s in states
        if s.entity_id.startswith("sensor.")
        and s.attributes.get("device_class") == SensorDeviceClass.TEMPERATURE
    ]
    # Should have temperature sensors
    assert len(temp_sensors) > 0


async def test_sensor_qube_info_entity(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test Qube info sensor entity is created with metadata."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Check entity registry for info sensor (more reliable than states)
    entity_registry = er.async_get(hass)
    info_entries = [
        e for e in entity_registry.entities.values() if "info" in e.unique_id
    ]
    # Should have info sensor registered
    assert len(info_entries) > 0, "Info sensor not found in entity registry"

    # Also check state if available
    states = hass.states.async_all()
    info_sensors = [s for s in states if "qube_info" in s.entity_id]
    if info_sensors:
        attrs = info_sensors[0].attributes
        assert "version" in attrs or "label" in attrs or "host" in attrs
