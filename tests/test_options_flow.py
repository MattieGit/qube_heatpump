"""Tests for the Qube Heat Pump options flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_NAME,
    DOMAIN,
)
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


async def test_options_flow_updates_options(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow successfully updates name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        title="qube 1",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        user_input={
            CONF_HOST: entry.data[CONF_HOST],
            CONF_NAME: "my heat pump",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_NAME] == "my heat pump"

    await hass.async_block_till_done()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_default_prefix(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow keeps default name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        title="qube 1",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        user_input={
            CONF_HOST: entry.data[CONF_HOST],
            CONF_NAME: "qube 1",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_NAME] == "qube 1"

    await hass.async_block_till_done()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_empty_host_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow shows error for empty host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        title="qube 1",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        user_input={
            CONF_HOST: "",
            CONF_NAME: "qube 1",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}

    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_duplicate_ip_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow shows error for duplicate IP."""
    from unittest.mock import patch

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        title="qube 1",
    )
    entry.add_to_hass(hass)

    # Add another entry with a different host
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.20", CONF_NAME: "qube 2"},
        unique_id=f"{DOMAIN}-192.0.2.20-502",
        title="qube 2",
    )
    other_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    with patch(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        return_value="192.0.2.20",
    ):
        result = await hass.config_entries.options.async_configure(
            init_result["flow_id"],
            user_input={
                CONF_HOST: "qube-new.local",
                CONF_NAME: "qube 1",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "duplicate_ip"}

    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_cannot_connect_error(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow shows error when cannot connect to new host."""
    from unittest.mock import patch

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        title="qube 1",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        side_effect=OSError("Connection refused"),
    ):
        result = await hass.config_entries.options.async_configure(
            init_result["flow_id"],
            user_input={
                CONF_HOST: "192.0.2.99",
                CONF_NAME: "qube 1",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_connect"}

    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_host_change_success(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Test that options flow successfully changes host."""
    from unittest.mock import AsyncMock, MagicMock, patch

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.10", CONF_NAME: "qube 1"},
        unique_id=f"{DOMAIN}-192.0.2.10-502",
        title="qube 1",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        return_value=(AsyncMock(), MagicMock()),
    ):
        result = await hass.config_entries.options.async_configure(
            init_result["flow_id"],
            user_input={
                CONF_HOST: "192.0.2.99",
                CONF_NAME: "qube 1",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_HOST] == "192.0.2.99"

    await hass.async_block_till_done()
