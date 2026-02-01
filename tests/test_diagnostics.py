"""Tests for the Qube Heat Pump diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from custom_components.qube_heatpump.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


async def test_diagnostics_returns_redacted_data(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test diagnostics returns properly redacted data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        title="Qube Heat Pump (test)",
        unique_id=f"{DOMAIN}-192.168.1.100-502",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Check structure
    assert "entry" in diagnostics
    assert "hub" in diagnostics
    assert "entities" in diagnostics

    # Check entry data is present
    assert "entry_id" in diagnostics["entry"]
    assert "data" in diagnostics["entry"]
    assert "options" in diagnostics["entry"]

    # Check hub data
    assert "label" in diagnostics["hub"]
    assert "multi_device" in diagnostics["hub"]

    # Check host is redacted
    assert diagnostics["hub"]["host"] == "**REDACTED**"
    assert diagnostics["hub"]["port"] == "**REDACTED**"

    # Check entities list is present and limited
    assert isinstance(diagnostics["entities"], list)
    assert len(diagnostics["entities"]) <= 10


async def test_diagnostics_includes_entity_info(
    hass: HomeAssistant,
    mock_qube_client: MagicMock,
) -> None:
    """Test diagnostics includes entity information."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Check entities have expected fields
    if diagnostics["entities"]:
        entity = diagnostics["entities"][0]
        assert "name" in entity
        assert "platform" in entity
        assert "address" in entity
        # unique_id should be redacted
        assert entity["unique_id"] == "**REDACTED**"


def test_to_redact_fields() -> None:
    """Test TO_REDACT contains expected fields."""
    assert "host" in TO_REDACT
    assert "port" in TO_REDACT
    assert "unique_id" in TO_REDACT
