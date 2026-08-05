"""Tests for the Qube Heat Pump virtual thermostat climate platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DOMAIN,
)
from homeassistant.components.climate import (
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import STATE_ON

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


async def _setup_thermostat_entry(hass: HomeAssistant) -> str:
    """Set up an entry with the virtual thermostat enabled and return its entity_id."""
    hass.states.async_set("sensor.outdoor_temperature", "18.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options={
            CONF_THERMOSTAT_ENABLED: True,
            CONF_THERMOSTAT_SENSOR: "sensor.outdoor_temperature",
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = hass.states.async_all()
    climate_states = [s for s in states if s.entity_id.startswith("climate.")]
    assert climate_states, "Thermostat climate entity was not created"
    return climate_states[0].entity_id


async def test_thermostat_supports_turn_on_and_turn_off(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Required since HA 2024.2 for climate entities exposing HVACMode.OFF."""
    entity_id = await _setup_thermostat_entry(hass)

    entity_registry_state = hass.states.get(entity_id)
    assert entity_registry_state is not None
    supported_features = entity_registry_state.attributes["supported_features"]

    assert supported_features & ClimateEntityFeature.TURN_ON
    assert supported_features & ClimateEntityFeature.TURN_OFF
    assert supported_features & ClimateEntityFeature.TARGET_TEMPERATURE


async def test_climate_turn_off_service_sets_hvac_off(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """The climate.turn_off service should be usable (not NotImplementedError)."""
    entity_id = await _setup_thermostat_entry(hass)

    await hass.services.async_call(
        "climate",
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.OFF


async def test_climate_turn_on_service_sets_hvac_mode(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """The climate.turn_on service should pick a non-OFF mode."""
    entity_id = await _setup_thermostat_entry(hass)

    # Start from OFF so turn_on has an observable effect.
    await hass.services.async_call(
        "climate",
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == HVACMode.OFF

    await hass.services.async_call(
        "climate",
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state != HVACMode.OFF
    assert state.state != STATE_ON
