from __future__ import annotations

from typing import Any
import asyncio
import contextlib

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlow

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_PORT,
    CONF_UNIT_ID,
    CONF_USE_VENDOR_NAMES,
    CONF_LABEL,
    CONF_SHOW_LABEL_IN_NAME,
)


class WPQubeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = DEFAULT_PORT

            # Validate connectivity to the device to provide immediate feedback
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=5
                )
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{DOMAIN}-{host}-{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"WP Qube ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            # Persist options
            return self.async_create_entry(title="", data=user_input)

        # Defaults from existing options or sensible defaults
        unit_id = self.config_entry.options.get(CONF_UNIT_ID, 1)
        use_vendor = self.config_entry.options.get(CONF_USE_VENDOR_NAMES, False)
        label = self.config_entry.options.get(CONF_LABEL, "qube1")
        show_label = self.config_entry.options.get(CONF_SHOW_LABEL_IN_NAME, False)
        schema = vol.Schema({
            vol.Required(CONF_UNIT_ID, default=unit_id): vol.Coerce(int),
            vol.Required(CONF_USE_VENDOR_NAMES, default=use_vendor): bool,
            vol.Required(CONF_LABEL, default=label): str,
            vol.Required(CONF_SHOW_LABEL_IN_NAME, default=show_label): bool,
        })
        # Description provided via translations
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlowHandler:
    return OptionsFlowHandler(config_entry)
