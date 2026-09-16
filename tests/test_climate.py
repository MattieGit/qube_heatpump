"""Tests for the Qube Heat Pump virtual thermostat climate platform."""

from __future__ import annotations

from datetime import timedelta
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DOMAIN,
    THERMOSTAT_SENSOR_TIMEOUT,
)
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import STATE_ON
from homeassistant.core import State

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from freezegun.api import FrozenDateTimeFactory

    from homeassistant.core import HomeAssistant

SENSOR_ENTITY_ID = "sensor.outdoor_temperature"
# The config entry has no CONF_NAME, so __init__.py's migration path assigns
# device_name "qube 1" (first entry) regardless of the MockConfigEntry title,
# which slugifies to the "qube_1" label used in generated entity_ids below.
CLIMATE_ENTITY_ID = "climate.qube_1_thermostat"
TIMEOUT_SENSOR_ENTITY_ID = "binary_sensor.qube_1_thermostat_sensor_timeout"


class FakeDevice:
    """Coil store standing in for the heat pump controller.

    The shared ``mock_qube_client`` returns 45.0 for every read, which makes
    both thermostat coils read as "on". The thermostat compares its flags
    against the coil values the coordinator polls, so the climate tests need
    reads to reflect writes: writes land in ``coils`` and reads return them.
    Keys listed in ``failing`` make ``write_switch`` report failure.
    """

    def __init__(self, mock_qube_client: MagicMock, **initial: bool) -> None:
        """Wire the mock client's read/write methods to this coil store."""
        self.coils: dict[str, bool] = {
            "modbus_demand": False,
            "bms_summerwinter": False,
            **initial,
        }
        self.failing: set[str] = set()
        mock_qube_client.read_entity = AsyncMock(side_effect=self._read)
        mock_qube_client.write_switch = AsyncMock(side_effect=self._write)

    async def _read(self, ent: Any) -> Any:
        key = getattr(ent, "key", None)
        if key in self.coils:
            return self.coils[key]
        return 45.0

    async def _write(self, key: str, on: bool) -> bool:
        if key in self.failing:
            return False
        self.coils[key] = on
        return True


async def _setup_thermostat_entry(
    hass: HomeAssistant, initial_temp: str = "18.0"
) -> str:
    """Set up an entry with the virtual thermostat enabled and return its entity_id."""
    hass.states.async_set(SENSOR_ENTITY_ID, initial_temp)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options={
            CONF_THERMOSTAT_ENABLED: True,
            CONF_THERMOSTAT_SENSOR: SENSOR_ENTITY_ID,
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = hass.states.async_all()
    climate_states = [s for s in states if s.entity_id.startswith("climate.")]
    assert climate_states, "Thermostat climate entity was not created"
    return climate_states[0].entity_id


def _demand_calls(mock_qube_client: MagicMock) -> list[bool]:
    """Return the sequence of values written to the modbus_demand switch."""
    return [
        call.args[1]
        for call in mock_qube_client.write_switch.call_args_list
        if call.args[0] == "modbus_demand"
    ]


def _summer_calls(mock_qube_client: MagicMock) -> list[bool]:
    """Return the sequence of values written to the bms_summerwinter switch."""
    return [
        call.args[1]
        for call in mock_qube_client.write_switch.call_args_list
        if call.args[0] == "bms_summerwinter"
    ]


async def _set_hvac_mode(
    hass: HomeAssistant, entity_id: str, hvac_mode: HVACMode
) -> None:
    """Call the climate.set_hvac_mode service and settle the event loop."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": hvac_mode},
        blocking=True,
    )
    await hass.async_block_till_done()


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


async def test_thermostat_not_created_when_disabled(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """No climate entity should be created when thermostat_enabled is falsy/absent."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate_states = [
        s for s in hass.states.async_all() if s.entity_id.startswith("climate.")
    ]
    assert climate_states == []


async def test_thermostat_not_created_when_sensor_missing(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """No climate entity should be created when thermostat_sensor option is unset."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
        options={CONF_THERMOSTAT_ENABLED: True},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate_states = [
        s for s in hass.states.async_all() if s.entity_id.startswith("climate.")
    ]
    assert climate_states == []


async def test_heat_mode_hysteresis(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """HEAT mode: demand flips on/off at the hysteresis edges and holds in the deadband."""
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")
    assert entity_id == CLIMATE_ENTITY_ID
    mock_qube_client.write_switch.reset_mock()

    # temp <= target - 0.3 (20.2) -> demand on
    hass.states.async_set(SENSOR_ENTITY_ID, "20.1")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [True]

    # Inside deadband while heating -> hysteresis holds, no new demand write
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.4")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == []

    # temp >= target + 0.3 (20.8) -> demand off
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.9")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False]


async def test_cool_mode_hysteresis_and_summer_switch(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """COOL mode: summer switch is written True and hysteresis is inverted vs HEAT."""
    FakeDevice(mock_qube_client)
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")
    mock_qube_client.write_switch.reset_mock()

    await _set_hvac_mode(hass, entity_id, HVACMode.COOL)
    assert True in _summer_calls(mock_qube_client)

    # temp >= target + 0.3 -> demand on (cooling)
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.9")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [True]

    # Inside deadband while cooling -> hysteresis holds
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.6")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == []

    # temp <= target - 0.3 -> demand off
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.1")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False]


async def test_heat_cool_mode_switches_summer_mode_and_demand(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """HEAT_COOL: both the summer switch and demand flip at each hysteresis edge."""
    device = FakeDevice(mock_qube_client)
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")
    mock_qube_client.write_switch.reset_mock()

    await _set_hvac_mode(hass, entity_id, HVACMode.HEAT_COOL)

    # Too cold -> heating: demand on; the coil already reads winter, so the
    # summer switch is not rewritten
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.1")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [True]
    assert _summer_calls(mock_qube_client) == []
    assert device.coils["bms_summerwinter"] is False

    # Too hot -> switches from heating to cooling in the same control pass
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.9")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False, True]
    assert True in _summer_calls(mock_qube_client)

    # Back to deadband while cooling -> hysteresis holds, keep cooling
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.5")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == []

    # Too cold again -> cooling stops and heating starts in one pass
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.1")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False, True]
    assert False in _summer_calls(mock_qube_client)


async def test_heat_cool_deadband_keeps_hysteresis(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """HEAT_COOL must not short-cycle: heating holds through the deadband.

    Regression test: the deadband branch used to turn demand off as soon as
    the temperature was no longer ``too_cold`` (the same threshold at which
    heating started), so demand toggled every time the reading crossed
    target - cold_tolerance.
    """
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")
    await _set_hvac_mode(hass, entity_id, HVACMode.HEAT_COOL)

    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.1")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [True]

    # Crossing target - 0.3 upward stays in the deadband: no demand write
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.3")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == []
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.HEATING

    hass.states.async_set(SENSOR_ENTITY_ID, "20.6")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == []

    # Only reaching target + 0.3 ends heating (and, in HEAT_COOL, starts cooling)
    hass.states.async_set(SENSOR_ENTITY_ID, "20.8")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False, True]
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.COOLING


async def test_off_mode_turns_off_demand(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Switching to OFF while heating turns the demand switch off."""
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.1")
    # Setup itself triggers the initial control pass which starts heating.
    assert True in _demand_calls(mock_qube_client)

    mock_qube_client.write_switch.reset_mock()
    await _set_hvac_mode(hass, entity_id, HVACMode.OFF)

    assert _demand_calls(mock_qube_client) == [False]
    assert hass.states.get(entity_id).state == HVACMode.OFF


async def test_async_set_temperature_updates_target(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """async_set_temperature should update the reported target temperature."""
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, "temperature": 22.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_TEMPERATURE] == 22.0


async def test_restore_state_restores_mode_and_target(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """RestoreEntity should bring back the previous hvac_mode and target temperature."""
    mock_restore_cache(
        hass,
        [
            State(
                CLIMATE_ENTITY_ID,
                HVACMode.COOL,
                {ATTR_TEMPERATURE: 23.5},
            )
        ],
    )

    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.5")
    assert entity_id == CLIMATE_ENTITY_ID

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_TEMPERATURE] == 23.5


async def test_sensor_timeout_turns_off_demand_and_sets_flag(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stale temperature sensor is treated as a safety timeout after 30 minutes."""
    FakeDevice(mock_qube_client)
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.1")
    # Setup itself triggers the initial control pass which starts heating.
    assert True in _demand_calls(mock_qube_client)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.thermostat_sensor_timed_out is False

    mock_qube_client.write_switch.reset_mock()
    future_monotonic = time.monotonic() + THERMOSTAT_SENSOR_TIMEOUT + 1
    with patch(
        "custom_components.qube_heatpump.climate.time.monotonic",
        return_value=future_monotonic,
    ):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert _demand_calls(mock_qube_client) == [False]
    assert entry.runtime_data.thermostat_sensor_timed_out is True

    timeout_state = hass.states.get(TIMEOUT_SENSOR_ENTITY_ID)
    assert timeout_state is not None
    assert timeout_state.state == STATE_ON

    # A fresh sensor reading clears the timeout flag again.
    hass.states.async_set(SENSOR_ENTITY_ID, "20.5")
    await hass.async_block_till_done()
    assert entry.runtime_data.thermostat_sensor_timed_out is False


async def test_sensor_timeout_recovery_reenables_heating_when_still_cold(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a timeout, demand must re-enable once the sensor reports a still-cold value.

    Regression test: `_async_check_timeout` used to turn demand off without
    resetting `_is_heating`, so `_async_control_heating`'s HEAT guard
    (`too_cold and not self._is_heating`) stayed False forever after recovery.
    """
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.1")
    # Setup itself triggers the initial control pass which starts heating.
    assert True in _demand_calls(mock_qube_client)

    mock_qube_client.write_switch.reset_mock()
    future_monotonic = time.monotonic() + THERMOSTAT_SENSOR_TIMEOUT + 1
    with patch(
        "custom_components.qube_heatpump.climate.time.monotonic",
        return_value=future_monotonic,
    ):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert _demand_calls(mock_qube_client) == [False]

    # Sensor recovers, but the reading is still well below target - tolerance
    # (target 20.5, tolerance 0.3 -> too_cold threshold 20.2).
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "19.0")
    await hass.async_block_till_done()

    assert _demand_calls(mock_qube_client) == [True]


async def test_failed_demand_write_does_not_set_flag_and_is_retried(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A failed modbus_demand write must not flip _is_heating; retry next pass.

    Regression test: the write helper swallowed the error and the caller set
    the heating flag anyway, so the thermostat believed it was heating while
    the coil stayed off and never retried.
    """
    device = FakeDevice(mock_qube_client)
    device.failing.add("modbus_demand")

    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.1")
    assert _demand_calls(mock_qube_client) == [True]
    assert device.coils["modbus_demand"] is False
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.IDLE

    # Device is reachable again; the next evaluation retries the write.
    device.failing.clear()
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.0")
    await hass.async_block_till_done()

    assert _demand_calls(mock_qube_client) == [True]
    assert device.coils["modbus_demand"] is True
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.HEATING


async def test_failed_demand_off_write_keeps_flag_and_is_retried(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A failed turn-off keeps _is_heating so the next pass tries again."""
    device = FakeDevice(mock_qube_client)
    entity_id = await _setup_thermostat_entry(hass, initial_temp="20.1")
    assert device.coils["modbus_demand"] is True

    device.failing.add("modbus_demand")
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "20.9")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False]
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.HEATING

    device.failing.clear()
    mock_qube_client.write_switch.reset_mock()
    hass.states.async_set(SENSOR_ENTITY_ID, "21.0")
    await hass.async_block_till_done()
    assert _demand_calls(mock_qube_client) == [False]
    assert device.coils["modbus_demand"] is False
    assert hass.states.get(entity_id).attributes["hvac_action"] == HVACAction.IDLE


async def test_summer_mode_not_rewritten_when_coordinator_agrees(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """bms_summerwinter is only written when the polled coil value differs.

    Regression test: every evaluation (each sensor state-change event) used
    to write the summer/winter coil unconditionally.
    """
    FakeDevice(mock_qube_client)  # bms_summerwinter already off (winter)
    await _setup_thermostat_entry(hass, initial_temp="20.5")
    assert _summer_calls(mock_qube_client) == []

    for temp in ("20.1", "20.4", "20.9", "20.3"):
        hass.states.async_set(SENSOR_ENTITY_ID, temp)
        await hass.async_block_till_done()
    assert _summer_calls(mock_qube_client) == []
    assert _demand_calls(mock_qube_client) == [True, False]


async def test_summer_mode_written_once_when_coil_differs(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """A mismatching coil is corrected once, then left alone."""
    device = FakeDevice(mock_qube_client, bms_summerwinter=True)
    await _setup_thermostat_entry(hass, initial_temp="20.5")
    assert _summer_calls(mock_qube_client) == [False]
    assert device.coils["bms_summerwinter"] is False

    # Further evaluations (no demand write involved) must not repeat the write.
    for temp in ("20.4", "20.6", "20.5"):
        hass.states.async_set(SENSOR_ENTITY_ID, temp)
        await hass.async_block_till_done()
    assert _summer_calls(mock_qube_client) == [False]


async def test_sensor_timeout_fires_when_sensor_never_valid(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The timeout must also trip when no valid reading ever arrived.

    Regression test: `_async_check_timeout` returned early while
    `_current_temp` was None, so a sensor that was unavailable from startup
    never raised the timeout flag.
    """
    FakeDevice(mock_qube_client)
    await _setup_thermostat_entry(hass, initial_temp="unavailable")
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.thermostat_sensor_timed_out is False
    assert _demand_calls(mock_qube_client) == []

    future_monotonic = time.monotonic() + THERMOSTAT_SENSOR_TIMEOUT + 1
    with patch(
        "custom_components.qube_heatpump.climate.time.monotonic",
        return_value=future_monotonic,
    ):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert entry.runtime_data.thermostat_sensor_timed_out is True
    # Demand was never on, so nothing is written to turn it off.
    assert _demand_calls(mock_qube_client) == []

    # First valid reading clears the flag and resumes control.
    hass.states.async_set(SENSOR_ENTITY_ID, "19.0")
    await hass.async_block_till_done()
    assert entry.runtime_data.thermostat_sensor_timed_out is False
    assert _demand_calls(mock_qube_client) == [True]
