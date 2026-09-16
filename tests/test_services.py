"""Tests for the Qube Heat Pump services."""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, CONF_NAME, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from . import setup_integration

# Writable registers used by the write_register tests; both addresses map to
# exactly one library entity.
HEAT_SETPOINT_ADDRESS = 101
HEAT_SETPOINT_KEY = "usr_pid_heatsetp"
DEMAND_COIL_ADDRESS = 67
DEMAND_COIL_KEY = "modbus_demand"


def _entry(host: str, name: str | None = None) -> MockConfigEntry:
    """Return an extra config entry for the multi-entry cases."""
    data: dict[str, Any] = {CONF_HOST: host}
    if name is not None:
        data[CONF_NAME] = name
    return MockConfigEntry(
        domain=DOMAIN,
        data=data,
        title=name or "Qube Heat Pump",
        unique_id=f"{DOMAIN}-{host}-502",
    )


async def test_services_registered_by_async_setup_alone(
    hass: HomeAssistant,
) -> None:
    """Services are registered at component setup, before any config entry exists.

    Registration lives in the module-level async_setup() so the services
    register once and survive individual config entries being unloaded.
    """
    assert not hass.services.has_service(DOMAIN, "reconfigure")
    assert not hass.services.has_service(DOMAIN, "write_register")

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "reconfigure")
    assert hass.services.has_service(DOMAIN, "write_register")


async def test_services_survive_last_entry_unload(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Services stay registered after the last config entry unloads.

    Calling write_register afterwards fails cleanly with a
    HomeAssistantError (no loaded entry to resolve) instead of the service
    disappearing from the registry.
    """
    await setup_integration(hass, mock_config_entry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "reconfigure")
    assert hass.services.has_service(DOMAIN, "write_register")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": HEAT_SETPOINT_ADDRESS, "value": 42.0},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("address", "value", "write", "expected_call"),
    [
        (
            HEAT_SETPOINT_ADDRESS,
            21.5,
            "write_setpoint",
            (HEAT_SETPOINT_KEY, 21.5),
        ),
        (DEMAND_COIL_ADDRESS, 1, "write_switch", (DEMAND_COIL_KEY, True)),
    ],
    ids=["holding_register", "coil"],
)
async def test_write_register_dispatches_by_platform(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    client_values: dict[str, Any],
    address: int,
    value: float,
    write: str,
    expected_call: tuple[str, Any],
) -> None:
    """The address picks the writable entity, which decides the write method."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        DOMAIN,
        "write_register",
        {"address": address, "value": value},
        blocking=True,
    )
    await hass.async_block_till_done()

    getattr(mock_qube_client, write).assert_awaited_once_with(*expected_call)
    # The controller now reports the written value back
    assert client_values[expected_call[0]] == expected_call[1]


async def test_write_register_resolves_the_entry_by_label(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """With two hubs loaded, the label decides which one is written to."""
    first = _entry("1.2.3.4", "qube1")
    second = _entry("1.2.3.5", "qube2")
    await setup_integration(hass, first)
    await setup_integration(hass, second)

    await hass.services.async_call(
        DOMAIN,
        "write_register",
        {"address": HEAT_SETPOINT_ADDRESS, "value": 21.5, "label": "qube2"},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_qube_client.write_setpoint.assert_awaited_once_with(HEAT_SETPOINT_KEY, 21.5)
    # Only the labelled hub's coordinator was asked to re-read
    assert second.runtime_data.coordinator.data[HEAT_SETPOINT_KEY] == 21.5
    assert first.runtime_data.coordinator.data[HEAT_SETPOINT_KEY] == 45.0


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"address": 99999, "value": 42.0}, "No writable entity"),
        (
            {"address": DEMAND_COIL_ADDRESS, "value": 0.4},
            "only accepts 0 or 1",
        ),
        (
            {"address": HEAT_SETPOINT_ADDRESS, "value": 42.0, "entry_id": "bogus"},
            "unable to resolve integration entry",
        ),
        (
            {"address": HEAT_SETPOINT_ADDRESS, "value": 42.0, "label": "nope"},
            "unable to resolve integration entry",
        ),
    ],
    ids=["unknown_address", "fractional_coil", "unknown_entry_id", "unknown_label"],
)
async def test_write_register_rejects_bad_requests(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    data: dict[str, Any],
    message: str,
) -> None:
    """A caller error raises instead of silently doing nothing."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError, match=message):
        await hass.services.async_call(DOMAIN, "write_register", data, blocking=True)

    mock_qube_client.write_setpoint.assert_not_awaited()
    mock_qube_client.write_switch.assert_not_awaited()


async def test_write_register_rejects_an_unloaded_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An explicit entry_id for an unloaded entry is refused.

    Home Assistant deletes ``runtime_data`` on unload rather than setting it
    to None, so the guard has to check the entry state. A second, loaded
    entry rules out the single-entry fallback in _resolve_entry.
    """
    await setup_integration(hass, mock_config_entry)
    await setup_integration(hass, _entry("1.2.3.5"))

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert not hasattr(mock_config_entry, "runtime_data")

    with pytest.raises(HomeAssistantError, match="not loaded"):
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {
                "address": HEAT_SETPOINT_ADDRESS,
                "value": 42.0,
                "entry_id": mock_config_entry.entry_id,
            },
            blocking=True,
        )


async def test_write_register_connect_failure_raises_translated_error(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A connect failure inside write_register is a translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    mock_qube_client.is_connected = False
    mock_qube_client.connect = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            "write_register",
            {"address": HEAT_SETPOINT_ADDRESS, "value": 50.0},
            blocking=True,
        )

    assert excinfo.value.translation_domain == DOMAIN
    assert excinfo.value.translation_key == "write_register_failed"
    assert excinfo.value.translation_placeholders == {
        "address": str(HEAT_SETPOINT_ADDRESS)
    }
    mock_qube_client.write_setpoint.assert_not_awaited()


async def test_reconfigure_starts_the_flow_for_the_only_entry(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without an entry_id the single config entry is reconfigured."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(DOMAIN, "reconfigure", {}, blocking=True)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reconfigure_confirm"
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_reconfigure_needs_an_entry_id_with_several_entries(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ambiguous call logs and starts nothing rather than guessing."""
    await setup_integration(hass, mock_config_entry)
    second = _entry("1.2.3.5")
    await setup_integration(hass, second)

    with caplog.at_level(logging.WARNING):
        await hass.services.async_call(DOMAIN, "reconfigure", {}, blocking=True)
        await hass.async_block_till_done()

    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert "pass entry_id" in caplog.text

    await hass.services.async_call(
        DOMAIN, "reconfigure", {"entry_id": second.entry_id}, blocking=True
    )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["entry_id"] == second.entry_id


async def test_reconfigure_survives_an_unavailable_flow(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A flow that refuses to start is logged, not raised at the caller."""
    await setup_integration(hass, mock_config_entry)

    with (
        patch.object(
            hass.config_entries.flow,
            "async_init",
            side_effect=HomeAssistantError("Flow error"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        await hass.services.async_call(DOMAIN, "reconfigure", {}, blocking=True)
        await hass.async_block_till_done()

    assert "Reconfigure flow not available" in caplog.text
