"""Test the Qube Heat Pump config flow."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, CONF_PORT, DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump (1.2.3.4)",
    )


async def test_form(hass: HomeAssistant, mock_setup_entry: MagicMock) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        return_value=(AsyncMock(), MagicMock()),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4"},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Qube Heat Pump (1.2.3.4)"
    assert result2["data"] == {
        CONF_HOST: "1.2.3.4",
        CONF_PORT: 502,
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        side_effect=OSError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_timeout(hass: HomeAssistant) -> None:
    """Test we handle timeout error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        side_effect=TimeoutError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_already_configured(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """Test we get duplicate_ip error when same host is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        return_value=(AsyncMock(), MagicMock()),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4"},
        )

    # Config flow returns form with duplicate_ip error when same host is configured
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"host": "duplicate_ip"}


async def test_form_duplicate_ip(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """Test we handle duplicate IP error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Try to configure with a hostname that resolves to the same IP
    with (
        patch(
            "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
            return_value=(AsyncMock(), MagicMock()),
        ),
        patch(
            "custom_components.qube_heatpump.config_flow._async_resolve_host",
            return_value="1.2.3.4",
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "qube.local"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"host": "duplicate_ip"}


async def test_form_with_existing_entries(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """Test the form when there are already existing entries (no default value)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the reconfigure flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"


async def test_reconfigure_confirm(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfigure confirmation updates entry."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    with patch(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        return_value="5.6.7.8",
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigured"
    assert mock_config_entry.data[CONF_HOST] == "5.6.7.8"


async def test_reconfigure_unknown_entry(hass: HomeAssistant) -> None:
    """Test reconfigure aborts when entry is unknown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": "nonexistent_entry",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown_entry"


async def test_reconfigure_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfigure aborts when unique_id already exists."""
    mock_config_entry.add_to_hass(hass)

    # Add another entry with the target unique_id
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-5.6.7.8-502",
    )
    other_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    with patch(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        return_value="5.6.7.8",
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reconfigure_duplicate_ip(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfigure aborts when IP conflicts with another entry."""
    mock_config_entry.add_to_hass(hass)

    # Add another entry with a different host that resolves to same IP
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-5.6.7.8-502",
    )
    other_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )

    with patch(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        return_value="5.6.7.8",
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "qube-new.local", CONF_PORT: 502},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "duplicate_ip"


async def test_form_empty_host(hass: HomeAssistant) -> None:
    """Test we get error for empty host (cannot connect)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Empty host will fail to connect
    with patch(
        "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
        side_effect=OSError("Invalid host"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: ""},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_resolve_host_dns(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """Test DNS resolution during config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.qube_heatpump.config_flow.asyncio.open_connection",
            return_value=(AsyncMock(), MagicMock()),
        ),
        patch(
            "asyncio.get_running_loop",
        ) as mock_loop,
    ):
        mock_loop.return_value.getaddrinfo = AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))
            ]
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "qube.local"},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
