"""Tests for the backup heater entities and the heater energy estimate."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.qube_heatpump.const import (
    CONF_HEATER_STEP_POWER,
    CONF_NAME,
    DEFAULT_SCAN_INTERVAL,
)
from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType

from . import async_poll, setup_integration

STEP_KEYS = ("dout_heaterstep1_val", "dout_heaterstep2_val", "dout_heaterstep3_val")
VALVE_KEY = "dout_threewayvlv_val"  # True = DHW, False = CH

BACKUP_CH = "binary_sensor.qube_1_backup_heater_ch"
BACKUP_DHW = "binary_sensor.qube_1_backup_heater_dhw"
STEPS = "sensor.qube_1_heater_steps_active"
ENERGY_CH = "sensor.qube_1_heater_energy_ch"
ENERGY_DHW = "sensor.qube_1_heater_energy_dhw"

STEP_POWER = 2500
POLL_SECONDS = DEFAULT_SCAN_INTERVAL + 1  # what async_poll advances the clock by


def _set_heaters(
    client_values: dict[str, Any], steps: int, valve: bool | None = False
) -> None:
    """Switch the first ``steps`` heater outputs on and set the valve."""
    for index, key in enumerate(STEP_KEYS):
        client_values[key] = index < steps
    client_values[VALVE_KEY] = valve


def _kwh(watts: float, seconds: float) -> float:
    return watts * seconds / 3_600_000


@pytest.mark.parametrize(
    ("steps", "valve", "expected_ch", "expected_dhw", "expected_steps"),
    [
        (0, False, STATE_OFF, STATE_OFF, "0"),
        (0, True, STATE_OFF, STATE_OFF, "0"),
        (1, False, STATE_ON, STATE_OFF, "1"),
        (2, False, STATE_ON, STATE_OFF, "2"),
        (3, True, STATE_OFF, STATE_ON, "3"),
        (1, True, STATE_OFF, STATE_ON, "1"),
    ],
)
async def test_backup_heater_sensors(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    steps: int,
    valve: bool,
    expected_ch: str,
    expected_dhw: str,
    expected_steps: str,
) -> None:
    """The binary sensors split heater use by the valve; the step count does not."""
    _set_heaters(client_values, steps, valve)
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(BACKUP_CH).state == expected_ch
    assert hass.states.get(BACKUP_DHW).state == expected_dhw
    assert hass.states.get(STEPS).state == expected_steps


async def test_only_the_second_step_counts(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
) -> None:
    """Any step output turns the heater on, not only step 1."""
    _set_heaters(client_values, 0)
    client_values["dout_heaterstep2_val"] = True
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(BACKUP_CH).state == STATE_ON
    assert hass.states.get(STEPS).state == "1"


@pytest.mark.parametrize("missing", [*STEP_KEYS, VALVE_KEY])
async def test_unavailable_without_readings(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    missing: str,
) -> None:
    """A missing step or valve reading makes the sensors unavailable, not off."""
    _set_heaters(client_values, 1)
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(BACKUP_CH).state == STATE_ON

    client_values[missing] = None
    await async_poll(hass, freezer)

    assert hass.states.get(BACKUP_CH).state == STATE_UNAVAILABLE
    assert hass.states.get(BACKUP_DHW).state == STATE_UNAVAILABLE
    expected_steps = STATE_UNAVAILABLE if missing in STEP_KEYS else "1"
    assert hass.states.get(STEPS).state == expected_steps


async def test_no_energy_estimate_without_the_option(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without a step power only the binary sensors and the step count exist."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(BACKUP_CH) is not None
    assert hass.states.get(ENERGY_CH) is None
    assert hass.states.get(ENERGY_DHW) is None


@pytest.mark.parametrize("config_entry_options", [{CONF_HEATER_STEP_POWER: STEP_POWER}])
async def test_energy_split_by_valve(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each interval is booked at the previous poll's steps and valve."""
    _set_heaters(client_values, 2, valve=False)
    await setup_integration(hass, mock_config_entry)
    assert float(hass.states.get(ENERGY_CH).state) == 0.0

    await async_poll(hass, freezer)
    await async_poll(hass, freezer)
    _set_heaters(client_values, 1, valve=True)
    await async_poll(hass, freezer)  # still booked at 2 steps on CH
    await async_poll(hass, freezer)  # 1 step on DHW

    expected_ch = _kwh(2 * STEP_POWER, 3 * POLL_SECONDS)
    expected_dhw = _kwh(STEP_POWER, POLL_SECONDS)
    assert float(hass.states.get(ENERGY_CH).state) == pytest.approx(
        expected_ch, abs=1e-3
    )
    assert float(hass.states.get(ENERGY_DHW).state) == pytest.approx(
        expected_dhw, abs=1e-3
    )


@pytest.mark.parametrize("config_entry_options", [{CONF_HEATER_STEP_POWER: STEP_POWER}])
async def test_energy_skips_gaps(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Intervals next to a missing reading, or longer than the cap, are not booked."""
    _set_heaters(client_values, 3, valve=False)
    await setup_integration(hass, mock_config_entry)

    await async_poll(hass, freezer)  # booked
    client_values[STEP_KEYS[0]] = None
    await async_poll(hass, freezer)  # ends on a missing reading: skipped
    client_values[STEP_KEYS[0]] = True
    await async_poll(hass, freezer)  # starts on a missing reading: skipped

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()  # longer than the cap: skipped
    await async_poll(hass, freezer)  # booked

    expected = _kwh(3 * STEP_POWER, 2 * POLL_SECONDS)
    assert float(hass.states.get(ENERGY_CH).state) == pytest.approx(expected, abs=1e-3)
    assert float(hass.states.get(ENERGY_DHW).state) == 0.0


@pytest.mark.parametrize("config_entry_options", [{CONF_HEATER_STEP_POWER: STEP_POWER}])
async def test_energy_restored_after_restart(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The total continues from the stored value; the downtime is not booked."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENERGY_CH, "12.5"),
                {"native_value": 12.5, "native_unit_of_measurement": "kWh"},
            )
        ],
    )
    _set_heaters(client_values, 1, valve=False)
    await setup_integration(hass, mock_config_entry)
    assert float(hass.states.get(ENERGY_CH).state) == 12.5

    await async_poll(hass, freezer)

    assert float(hass.states.get(ENERGY_CH).state) == pytest.approx(
        12.5 + _kwh(STEP_POWER, POLL_SECONDS), abs=1e-3
    )


async def _submit_options(
    hass: HomeAssistant, entry: MockConfigEntry, extra: dict[str, Any]
) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: entry.data[CONF_HOST],
            CONF_NAME: entry.data[CONF_NAME],
            **extra,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_set_change_and_clear_step_power(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Setting the step power adds the estimates; clearing it removes them."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENERGY_CH) is None

    await _submit_options(hass, mock_config_entry, {CONF_HEATER_STEP_POWER: 2500})
    assert mock_config_entry.options[CONF_HEATER_STEP_POWER] == 2500
    assert hass.states.get(ENERGY_CH) is not None
    assert hass.states.get(ENERGY_DHW) is not None

    await _submit_options(hass, mock_config_entry, {CONF_HEATER_STEP_POWER: 800})
    assert mock_config_entry.options[CONF_HEATER_STEP_POWER] == 800
    assert hass.states.get(ENERGY_CH) is not None

    await _submit_options(hass, mock_config_entry, {})
    assert CONF_HEATER_STEP_POWER not in mock_config_entry.options
    # The registry keeps the orphaned entities, which Home Assistant shows as
    # restored and unavailable until the user deletes them
    for entity_id in (ENERGY_CH, ENERGY_DHW):
        state = hass.states.get(entity_id)
        assert state.state == STATE_UNAVAILABLE
        assert state.attributes.get("restored") is True


async def test_options_zero_step_power_turns_the_estimate_off(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A step power of 0 is the same as no step power."""
    await setup_integration(hass, mock_config_entry)

    await _submit_options(hass, mock_config_entry, {CONF_HEATER_STEP_POWER: 0})

    assert CONF_HEATER_STEP_POWER not in mock_config_entry.options
    assert hass.states.get(ENERGY_CH) is None
