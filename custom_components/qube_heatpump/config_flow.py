from __future__ import annotations

from typing import Any
import asyncio
import contextlib
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_RECONFIGURE
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
    _reconfig_entry: config_entries.ConfigEntry | None = None

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

    async def async_step_reconfigure(self, entry_data: dict | None = None):
        # Called when reconfigure flow is started; entry may be provided in context or data
        if entry_data and isinstance(entry_data, dict):
            eid = entry_data.get("entry_id")
            if eid:
                self._reconfig_entry = self.hass.config_entries.async_get_entry(eid)
        if self._reconfig_entry is None:
            # Try to get from context
            eid = (self.context or {}).get("entry_id")
            if eid:
                self._reconfig_entry = self.hass.config_entries.async_get_entry(eid)
        if self._reconfig_entry is None:
            return self.async_abort(reason="unknown_entry")

        # Show form
        data = self._reconfig_entry.data
        host = data.get(CONF_HOST)
        port = data.get(CONF_PORT, DEFAULT_PORT)
        schema = vol.Schema(
            {vol.Required(CONF_HOST, default=host): str, vol.Required(CONF_PORT, default=port): int}
        )
        return self.async_show_form(step_id="reconfigure_confirm", data_schema=schema)

    async def async_step_reconfigure_confirm(self, user_input: dict[str, Any]):
        if self._reconfig_entry is None:
            return self.async_abort(reason="unknown_entry")
        # Update entry data
        new = dict(self._reconfig_entry.data)
        new[CONF_HOST] = user_input[CONF_HOST]
        new[CONF_PORT] = user_input[CONF_PORT]
        self.hass.config_entries.async_update_entry(self._reconfig_entry, data=new)
        # Reload
        await self.hass.config_entries.async_reload(self._reconfig_entry.entry_id)
        return self.async_abort(reason="reconfigured")


_LOGGER = logging.getLogger(__name__)

"""
Options UI has been removed in favor of per-device entities.
Reconfigure flow is available to change host/port when triggered by a service.
"""
