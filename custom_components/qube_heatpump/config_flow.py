from __future__ import annotations

from typing import Any
import asyncio
import contextlib
import logging
import socket
import ipaddress

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.config_entries import OptionsFlow
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_PORT,
    CONF_UNIT_ID,
    CONF_LABEL,
    CONF_SHOW_LABEL_IN_NAME,
)


class WPQubeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _reconfig_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        return OptionsFlowHandler(config_entry)

    async def _async_resolve_host(self, host: str) -> str | None:
        """Resolve a host or IP string to a canonical IP address."""
        if not host:
            return None
        try:
            return str(ipaddress.ip_address(host))
        except Exception:
            pass

        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM,
            )
        except Exception:
            return None

        for family, _, _, _, sockaddr in infos:
            if not sockaddr:
                continue
            addr = sockaddr[0]
            if not isinstance(addr, str):
                continue
            if family == socket.AF_INET6 and addr.startswith("::ffff:"):
                addr = addr.removeprefix("::ffff:")
            return addr
        return None

    async def _async_has_conflicting_host(self, host: str, skip_entry_id: str | None = None) -> bool:
        """Check if host resolves to an IP already used by another entry."""
        candidate_ip = await self._async_resolve_host(host)
        for entry in self._async_current_entries():
            if skip_entry_id and entry.entry_id == skip_entry_id:
                continue
            existing_host = entry.data.get(CONF_HOST)
            if not existing_host:
                continue
            if existing_host == host:
                _LOGGER.debug("Host %s already configured; blocking duplicate", host)
                return True
            existing_ip = await self._async_resolve_host(existing_host)
            if candidate_ip and existing_ip and existing_ip == candidate_ip:
                _LOGGER.debug(
                    "Host %s resolves to %s already used by entry %s; blocking duplicate",
                    host,
                    candidate_ip,
                    entry.entry_id,
                )
                return True
        return False

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
                if await self._async_has_conflicting_host(host):
                    errors["host"] = "duplicate_ip"
                else:
                    await self.async_set_unique_id(f"{DOMAIN}-{host}-{port}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"WP Qube ({host})",
                        data={CONF_HOST: host, CONF_PORT: port},
                    )

        schema = vol.Schema({vol.Required(CONF_HOST, default="qube.local"): str})
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
        new_host = user_input[CONF_HOST]
        new_port = user_input[CONF_PORT]
        new_unique_id = f"{DOMAIN}-{new_host}-{new_port}"
        for entry in self._async_current_entries():
            if entry.entry_id == self._reconfig_entry.entry_id:
                continue
            if entry.unique_id == new_unique_id:
                return self.async_abort(reason="already_configured")

        if await self._async_has_conflicting_host(new_host, skip_entry_id=self._reconfig_entry.entry_id):
            return self.async_abort(reason="duplicate_ip")

        new = dict(self._reconfig_entry.data)
        new[CONF_HOST] = new_host
        new[CONF_PORT] = new_port
        self.hass.config_entries.async_update_entry(
            self._reconfig_entry,
            data=new,
            title=f"WP Qube ({new_host})",
            unique_id=new_unique_id,
        )
        # Reload
        await self.hass.config_entries.async_reload(self._reconfig_entry.entry_id)
        return self.async_abort(reason="reconfigured")


_LOGGER = logging.getLogger(__name__)

"""
Options Flow
Reconfigure flow is available to change host/port when triggered by a service.
Adds an option to show the hub label in entity names for sensors/switches.
The option is effective primarily for multi-device setups.
"""
class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        # Determine if multiple Qube entries exist to hint when label suffix becomes effective
        entries = [
            e for e in self.hass.config_entries.async_entries(DOMAIN) if e.entry_id != self._entry.entry_id
        ]
        multi_device = len(entries) >= 1

        if user_input is not None:
            unit_raw = user_input.get(CONF_UNIT_ID)
            try:
                unit_int = int(str(unit_raw).strip())
                if unit_int < 1 or unit_int > 247:
                    raise ValueError
            except (ValueError, TypeError):
                errors[CONF_UNIT_ID] = "invalid_unit_id"
            else:
                opts = dict(self._entry.options)
                opts[CONF_UNIT_ID] = unit_int
                opts[CONF_SHOW_LABEL_IN_NAME] = bool(user_input.get(CONF_SHOW_LABEL_IN_NAME, False))
                self.hass.config_entries.async_update_entry(self._entry, options=opts)
                return self.async_create_entry(title="", data=opts)

        import voluptuous as vol

        current_unit = int(
            self._entry.options.get(CONF_UNIT_ID, self._entry.data.get(CONF_UNIT_ID, 1))
        )
        current_label_option = bool(self._entry.options.get(CONF_SHOW_LABEL_IN_NAME, False))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UNIT_ID,
                    default=str(current_unit),
                ): str,
                vol.Optional(CONF_SHOW_LABEL_IN_NAME, default=current_label_option): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
