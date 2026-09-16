"""Tests for the Qube Heat Pump select platform."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.qube_heatpump.const import DOMAIN
from custom_components.qube_heatpump.select import BITS_TO_MODE, MODE_TO_BITS
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import setup_integration

SG_READY_MODE = "select.qube_1_sg_ready_mode"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every select entity."""
    with patch("custom_components.qube_heatpump.PLATFORMS", [Platform.SELECT]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_sgready_coils_have_no_switch_entities(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The SG Ready coils are only exposed through the select entity."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get("switch.qube_1_bms_sgready_a") is None
    assert hass.states.get("switch.qube_1_bms_sgready_b") is None
    assert hass.states.get(SG_READY_MODE) is not None


@pytest.mark.parametrize(
    ("coil_a", "coil_b", "option"),
    [
        (False, False, "Off"),
        (True, False, "Block"),
        (False, True, "Plus"),
        (True, True, "Max"),
    ],
)
async def test_select_current_option_from_coils(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    coil_a: bool,
    coil_b: bool,
    option: str,
) -> None:
    """The mode is decoded from the two SG Ready coils (and the maps agree)."""
    assert MODE_TO_BITS[option] == (coil_a, coil_b)
    assert BITS_TO_MODE[(coil_a, coil_b)] == option

    client_values.update({"bms_sgready_a": coil_a, "bms_sgready_b": coil_b})
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(SG_READY_MODE).state == option


@pytest.mark.parametrize(
    "client_values", [{"bms_sgready_a": None, "bms_sgready_b": True}]
)
async def test_select_current_option_unknown_when_coil_missing(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """With one coil unreadable the mode is unknown rather than an assumed default."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(SG_READY_MODE).state == "unknown"


@pytest.mark.parametrize(
    ("option", "expected_writes"),
    [
        ("Off", []),
        ("Block", [call("bms_sgready_a", True)]),
        ("Plus", [call("bms_sgready_b", True)]),
        ("Max", [call("bms_sgready_a", True), call("bms_sgready_b", True)]),
    ],
)
async def test_select_option_writes_only_changed_coils(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    option: str,
    expected_writes: list[Any],
) -> None:
    """Selecting a mode from Off writes just the coil(s) that differ."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(SG_READY_MODE).state == "Off"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SG_READY_MODE, "option": option},
        blocking=True,
    )

    assert mock_qube_client.write_switch.await_args_list == expected_writes
    assert hass.states.get(SG_READY_MODE).state == option


async def test_select_option_write_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A rejected coil write surfaces as a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.write_switch = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SG_READY_MODE, "option": "Max"},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_switch_failed"
    assert excinfo.value.translation_placeholders == {"entity_id": SG_READY_MODE}
    assert hass.states.get(SG_READY_MODE).state == "Off"
