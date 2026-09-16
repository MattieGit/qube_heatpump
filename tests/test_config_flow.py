"""Test the Qube Heat Pump config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState, UnknownEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

RESOLVE_HOST = "custom_components.qube_heatpump.config_flow.async_resolve_host"
OPEN_CONNECTION = "custom_components.qube_heatpump.config_flow.asyncio.open_connection"


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502, CONF_NAME: "qube 1"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="qube 1",
    )


def _tcp_ok():
    writer = MagicMock(wait_closed=AsyncMock())
    return patch(OPEN_CONNECTION, return_value=(AsyncMock(), writer))


async def test_form(hass: HomeAssistant, mock_setup_entry: MagicMock) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with _tcp_ok():
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_NAME: "qube 1"},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "qube 1"
    assert result2["data"] == {
        CONF_HOST: "1.2.3.4",
        CONF_PORT: 502,
        CONF_NAME: "qube 1",
    }
    assert result2["result"].unique_id == f"{DOMAIN}-1.2.3.4-502"
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "side_effect", [OSError, TimeoutError, OSError("Invalid host")]
)
async def test_form_cannot_connect(
    hass: HomeAssistant, side_effect: type[Exception] | Exception
) -> None:
    """A refused, timed-out or invalid host shows cannot_connect on the host field."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(OPEN_CONNECTION, side_effect=side_effect):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {CONF_HOST: "cannot_connect"}


async def test_form_recovers_after_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """The flow can be completed after a failed connection attempt."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(OPEN_CONNECTION, side_effect=OSError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )
    assert result["errors"] == {CONF_HOST: "cannot_connect"}

    with _tcp_ok():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    "host", ["1.2.3.4", "qube.local"], ids=["same_host", "resolves_to_same_ip"]
)
async def test_form_duplicate_ip(
    hass: HomeAssistant, mock_setup_entry: MagicMock, host: str
) -> None:
    """A host already configured, literally or after DNS, is rejected."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with _tcp_ok(), patch(RESOLVE_HOST, return_value="1.2.3.4"):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: host}
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {CONF_HOST: "duplicate_ip"}
    assert len(mock_setup_entry.mock_calls) == 0


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
    defaults = {
        str(key): None if key.default is vol.UNDEFINED else key.default()
        for key in result["data_schema"].schema
    }
    assert defaults[CONF_HOST] is None
    assert defaults[CONF_NAME] == "qube 2"


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The reconfigure flow shows the current settings as defaults."""
    mock_config_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults == {CONF_HOST: "1.2.3.4", CONF_PORT: 502, CONF_NAME: "qube 1"}


async def test_reconfigure_confirm(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_qube_client: MagicMock,
) -> None:
    """Reconfiguring updates data, title and unique_id, then reloads the entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await _start_reconfigure(hass, mock_config_entry)
    with _tcp_ok(), patch(RESOLVE_HOST, return_value="5.6.7.8"):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 503, CONF_NAME: "garage"},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {
        CONF_HOST: "5.6.7.8",
        CONF_PORT: 503,
        CONF_NAME: "garage",
    }
    assert mock_config_entry.title == "garage"
    assert mock_config_entry.unique_id == f"{DOMAIN}-5.6.7.8-503"
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_unknown_entry(hass: HomeAssistant) -> None:
    """Reconfigure for an entry id HA does not know raises UnknownEntry."""
    with pytest.raises(UnknownEntry):
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": "nonexistent_entry",
            },
        )


async def test_reconfigure_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring onto another entry's host/port aborts."""
    mock_config_entry.add_to_hass(hass)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-5.6.7.8-502",
    )
    other_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)
    with patch(RESOLVE_HOST, return_value="5.6.7.8"):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reconfigure_duplicate_ip(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A host resolving to another entry's IP is shown as a form error."""
    mock_config_entry.add_to_hass(hass)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        unique_id=f"{DOMAIN}-5.6.7.8-502",
    )
    other_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)
    with _tcp_ok(), patch(RESOLVE_HOST, return_value="5.6.7.8"):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "qube-new.local", CONF_PORT: 502},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "reconfigure_confirm"
    assert result2["errors"] == {CONF_HOST: "duplicate_ip"}
    assert mock_config_entry.data[CONF_HOST] == "1.2.3.4"


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """An unreachable new host is shown as a form error and nothing is changed."""
    mock_config_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)
    with patch(OPEN_CONNECTION, side_effect=OSError):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 502},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {CONF_HOST: "cannot_connect"}
    assert mock_config_entry.data[CONF_HOST] == "1.2.3.4"


async def test_form_stores_the_host_name_not_the_resolved_ip(
    hass: HomeAssistant, mock_setup_entry: MagicMock
) -> None:
    """A host name is only resolved to spot duplicates; the entry keeps the name.

    A DHCP lease may move the controller, so the name has to survive.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with _tcp_ok(), patch(RESOLVE_HOST, return_value="192.168.1.50") as resolve:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "qube.local"}
        )
        await hass.async_block_till_done()

    resolve.assert_awaited_with("qube.local")
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_HOST] == "qube.local"
    assert result2["result"].unique_id == f"{DOMAIN}-qube.local-502"
