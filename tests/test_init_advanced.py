"""Edge cases of the Qube Heat Pump entry setup."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, CONF_UNIT_ID, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import setup_integration


@pytest.mark.parametrize(
    ("data_unit", "option_unit", "expected"),
    [
        (None, None, 1),
        (3, None, 3),
        (3, 7, 7),
    ],
    ids=["default", "legacy_data", "option_overrides_data"],
)
async def test_unit_id_resolution(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_qube_client: MagicMock,
    data_unit: int | None,
    option_unit: int | None,
    expected: int,
) -> None:
    """The unit id comes from the options, then legacy entry data, then 1.

    It is part of the device identifier, so resolving it differently would
    split one device into two.
    """
    data: dict[str, Any] = {CONF_HOST: "1.2.3.4"}
    if data_unit is not None:
        data[CONF_UNIT_ID] = data_unit
    options = {} if option_unit is None else {CONF_UNIT_ID: option_unit}
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, title="Qube Heat Pump", options=options
    )

    await setup_integration(hass, entry)

    assert entry.runtime_data.hub.unit == expected
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"1.2.3.4:{expected}")}
    )


async def test_alarm_group_name_is_scoped_when_several_devices_exist(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A second heat pump gets a labelled alarm group so the two are tellable apart."""
    await setup_integration(hass, mock_config_entry)
    second = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.5"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.5-502",
    )
    await setup_integration(hass, second)

    first_group = hass.states.get("group.qube_alarms_qube_1")
    second_group = hass.states.get("group.qube_alarms_qube_2")
    assert first_group.attributes["friendly_name"] == "Qube alarm sensors"
    assert second_group.attributes["friendly_name"] == "Qube alarm sensors (qube_2)"
    assert all(
        entity_id.startswith("binary_sensor.qube_2_")
        for entity_id in second_group.attributes["entity_id"]
    )


async def test_setup_survives_a_failing_entity_registration(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """One entity that cannot be registered must not take the whole entry down."""
    original = entity_registry.async_get_or_create
    calls = 0

    def _fail_first_two(*args: Any, **kwargs: Any) -> er.RegistryEntry:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise ValueError("registry is busy")
        return original(*args, **kwargs)

    with patch.object(
        entity_registry, "async_get_or_create", side_effect=_fail_first_two
    ):
        await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert calls > 2
    assert hass.states.get("sensor.qube_1_temp_supply") is not None
