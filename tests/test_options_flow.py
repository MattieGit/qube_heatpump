from __future__ import annotations

import sys
import types

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_FRIENDLY_NAME_LANGUAGE,
    CONF_SHOW_LABEL_IN_NAME,
    CONF_UNIT_ID,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_options_flow_updates_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10"})
    entry.add_to_hass(hass)

    # Provide a stub modbus dependency so the options flow can load without the real component
    modbus_module = types.ModuleType("homeassistant.components.modbus")

    async def _async_setup(hass, config):  # pragma: no cover - simple stub
        return True

    modbus_module.async_setup = _async_setup
    modbus_module.DOMAIN = "modbus"
    sys.modules.setdefault("homeassistant.components.modbus", modbus_module)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        user_input={
            CONF_HOST: entry.data[CONF_HOST],
            CONF_SHOW_LABEL_IN_NAME: True,
            CONF_FRIENDLY_NAME_LANGUAGE: "en",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SHOW_LABEL_IN_NAME] is True
    assert entry.options[CONF_FRIENDLY_NAME_LANGUAGE] == "en"
    assert CONF_UNIT_ID not in entry.options

    await hass.async_block_till_done()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    sys.modules.pop("homeassistant.components.modbus", None)
