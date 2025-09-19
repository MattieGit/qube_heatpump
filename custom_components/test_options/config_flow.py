from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

DOMAIN = "test_options"


class TestOptionsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Test Options", data={})
        # No required fields; add directly
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))


class TestOptionsOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options or {}
        schema = vol.Schema(
            {
                vol.Optional("demo_text", default=opts.get("demo_text", "Hello")): str,
                vol.Optional("demo_bool", default=opts.get("demo_bool", False)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return TestOptionsOptionsFlow(config_entry)

