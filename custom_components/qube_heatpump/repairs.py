from __future__ import annotations

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN


class RegistryMigrationFlow(RepairsFlow):
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            await self.hass.services.async_call(
                DOMAIN, "migrate_registry", user_input, blocking=True
            )
            return self.async_create_entry(title="Entity registry migration", data={})

        schema = vol.Schema(
            {
                vol.Optional("dry_run", default=True): cv.boolean,
                vol.Optional("prefer_vendor_only", default=True): cv.boolean,
                vol.Optional("enforce_label_suffix", default=True): cv.boolean,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict | None):
    return RegistryMigrationFlow(hass)
