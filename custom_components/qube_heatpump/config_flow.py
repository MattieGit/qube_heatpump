"""Config flow for Qube Heat Pump integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_DHW_END_TIME,
    CONF_DHW_SCHEDULE_ENABLED,
    CONF_DHW_SETPOINT,
    CONF_DHW_START_TIME,
    CONF_DHW_USE_CONTROLLER_SETPOINT,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DEFAULT_DHW_END_TIME,
    DEFAULT_DHW_SETPOINT,
    DEFAULT_DHW_START_TIME,
    DEFAULT_DHW_USE_CONTROLLER_SETPOINT,
    DEFAULT_PORT,
    DOMAIN,
)
from .helpers import async_resolve_host

if TYPE_CHECKING:
    from collections.abc import Iterable

_LOGGER = logging.getLogger(__name__)

DOCS_URL = "https://github.com/MattieGit/qube_heatpump/tree/main/wiki"
CONNECT_TIMEOUT = 5

THERMOSTAT_KEYS = (CONF_THERMOSTAT_SENSOR,)
DHW_KEYS = (
    CONF_DHW_USE_CONTROLLER_SETPOINT,
    CONF_DHW_SETPOINT,
    CONF_DHW_START_TIME,
    CONF_DHW_END_TIME,
)


def _unique_id(host: str, port: int) -> str:
    return f"{DOMAIN}-{host}-{port}"


async def _async_find_conflicting_entry(
    entries: Iterable[ConfigEntry], host: str
) -> ConfigEntry | None:
    """Return an entry whose host resolves to the same address as ``host``."""
    candidate_ip = await async_resolve_host(host)
    for entry in entries:
        existing_host = entry.data.get(CONF_HOST)
        if not existing_host:
            continue
        if existing_host == host:
            return entry
        existing_ip = await async_resolve_host(existing_host)
        if candidate_ip and existing_ip == candidate_ip:
            return entry
    return None


async def _async_validate_host(
    hass: HomeAssistant, host: str, port: int, *, skip_entry_id: str | None = None
) -> str | None:
    """Validate a host for a new or changed entry.

    Returns an error key (``duplicate_ip`` or ``cannot_connect``) or None when
    the host is unique among the other entries and accepts a TCP connection.
    """
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != skip_entry_id
    ]
    if conflict := await _async_find_conflicting_entry(entries, host):
        _LOGGER.debug(
            "Host %s is already used by entry %s; blocking duplicate",
            host,
            conflict.entry_id,
        )
        return "duplicate_ip"

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=CONNECT_TIMEOUT
        )
    except (OSError, TimeoutError):
        return "cannot_connect"
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return None


class QubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qube Heat Pump."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return OptionsFlowHandler()

    def _default_name(self) -> str:
        """Generate the default device name based on existing entries."""
        return f"qube {len(self._async_current_entries()) + 1}"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            name = user_input.get(CONF_NAME, "").strip() or self._default_name()
            port = DEFAULT_PORT

            if error := await _async_validate_host(self.hass, host, port):
                errors[CONF_HOST] = error
            else:
                await self.async_set_unique_id(_unique_id(host, port))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_NAME: name},
                )

        host_field = (
            vol.Required(CONF_HOST)
            if self._async_current_entries()
            else vol.Required(CONF_HOST, default="qube.local")
        )
        schema = vol.Schema(
            {
                host_field: str,
                vol.Optional(CONF_NAME, default=self._default_name()): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"docs_url": DOCS_URL},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start reconfiguration: show the current connection settings."""
        return self._show_reconfigure_form(self._get_reconfigure_entry(), {})

    async def async_step_reconfigure_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and apply the new host, port and name."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self._show_reconfigure_form(entry, {})

        host = user_input[CONF_HOST]
        port = user_input[CONF_PORT]
        name = user_input.get(CONF_NAME, "").strip() or entry.title
        unique_id = _unique_id(host, port)
        for other in self._async_current_entries():
            if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                return self.async_abort(reason="already_configured")

        error = await _async_validate_host(
            self.hass, host, port, skip_entry_id=entry.entry_id
        )
        if error:
            return self._show_reconfigure_form(entry, {CONF_HOST: error})

        return self.async_update_reload_and_abort(
            entry,
            data_updates={CONF_HOST: host, CONF_PORT: port, CONF_NAME: name},
            title=name,
            unique_id=unique_id,
        )

    def _show_reconfigure_form(
        self, entry: ConfigEntry, errors: dict[str, str]
    ) -> ConfigFlowResult:
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                vol.Required(
                    CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Required(
                    CONF_NAME, default=entry.data.get(CONF_NAME) or entry.title
                ): str,
            }
        )
        return self.async_show_form(
            step_id="reconfigure_confirm", data_schema=schema, errors=errors
        )


class OptionsFlowHandler(OptionsFlow):
    """Options flow for Qube Heat Pump."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._user_input: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options - step 1: host, name, feature toggles."""
        errors: dict[str, str] = {}
        entry = self.config_entry
        current_host = str(entry.data.get(CONF_HOST, "qube.local")).strip()
        current_port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
        current_name = entry.data.get(CONF_NAME) or entry.title

        if user_input is not None:
            new_host = str(user_input.get(CONF_HOST, current_host)).strip()
            new_name = (
                str(user_input.get(CONF_NAME, current_name)).strip() or current_name
            )
            host_changed = new_host != current_host

            if not new_host:
                errors[CONF_HOST] = "invalid_host"
            elif host_changed and (
                error := await _async_validate_host(
                    self.hass, new_host, current_port, skip_entry_id=entry.entry_id
                )
            ):
                errors[CONF_HOST] = error

            if not errors:
                self._user_input = {
                    CONF_HOST: new_host,
                    CONF_NAME: new_name,
                    CONF_THERMOSTAT_ENABLED: bool(
                        user_input.get(CONF_THERMOSTAT_ENABLED, False)
                    ),
                    CONF_DHW_SCHEDULE_ENABLED: bool(
                        user_input.get(CONF_DHW_SCHEDULE_ENABLED, False)
                    ),
                }
                if self._user_input[CONF_THERMOSTAT_ENABLED]:
                    return await self.async_step_thermostat()
                if self._user_input[CONF_DHW_SCHEDULE_ENABLED]:
                    return await self.async_step_dhw_schedule()
                return self._save_options()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): str,
                vol.Required(CONF_NAME, default=current_name): str,
                vol.Optional(
                    CONF_THERMOSTAT_ENABLED,
                    default=bool(entry.options.get(CONF_THERMOSTAT_ENABLED, False)),
                ): bool,
                vol.Optional(
                    CONF_DHW_SCHEDULE_ENABLED,
                    default=bool(entry.options.get(CONF_DHW_SCHEDULE_ENABLED, False)),
                ): bool,
            }
        )
        resolved_ip = await async_resolve_host(current_host)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "resolved_ip": resolved_ip or "unknown",
                "docs_url": DOCS_URL,
            },
        )

    async def async_step_thermostat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: configure thermostat sensor."""
        if user_input is not None:
            self._user_input[CONF_THERMOSTAT_SENSOR] = user_input.get(
                CONF_THERMOSTAT_SENSOR, ""
            )
            if self._user_input.get(CONF_DHW_SCHEDULE_ENABLED):
                return await self.async_step_dhw_schedule()
            return self._save_options()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_THERMOSTAT_SENSOR,
                    default=self.config_entry.options.get(CONF_THERMOSTAT_SENSOR, ""),
                ): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
            }
        )
        return self.async_show_form(step_id="thermostat", data_schema=schema)

    async def async_step_dhw_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: configure DHW schedule."""
        options = self.config_entry.options
        if user_input is not None:
            self._user_input[CONF_DHW_USE_CONTROLLER_SETPOINT] = bool(
                user_input.get(
                    CONF_DHW_USE_CONTROLLER_SETPOINT,
                    DEFAULT_DHW_USE_CONTROLLER_SETPOINT,
                )
            )
            self._user_input[CONF_DHW_SETPOINT] = user_input.get(
                CONF_DHW_SETPOINT, DEFAULT_DHW_SETPOINT
            )
            self._user_input[CONF_DHW_START_TIME] = user_input.get(
                CONF_DHW_START_TIME, DEFAULT_DHW_START_TIME
            )
            self._user_input[CONF_DHW_END_TIME] = user_input.get(
                CONF_DHW_END_TIME, DEFAULT_DHW_END_TIME
            )
            return self._save_options()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DHW_USE_CONTROLLER_SETPOINT,
                    default=bool(
                        options.get(
                            CONF_DHW_USE_CONTROLLER_SETPOINT,
                            DEFAULT_DHW_USE_CONTROLLER_SETPOINT,
                        )
                    ),
                ): bool,
                vol.Required(
                    CONF_DHW_SETPOINT,
                    default=options.get(CONF_DHW_SETPOINT, DEFAULT_DHW_SETPOINT),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=40, max=65, step=0.5, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_DHW_START_TIME,
                    default=options.get(CONF_DHW_START_TIME, DEFAULT_DHW_START_TIME),
                ): TimeSelector(),
                vol.Required(
                    CONF_DHW_END_TIME,
                    default=options.get(CONF_DHW_END_TIME, DEFAULT_DHW_END_TIME),
                ): TimeSelector(),
            }
        )
        return self.async_show_form(step_id="dhw_schedule", data_schema=schema)

    def _save_options(self) -> ConfigFlowResult:
        """Persist the accumulated input.

        Host and name live in the entry data; feature settings in the options.
        Everything is written in one update so the entry's update listener
        reloads the integration exactly once.
        """
        entry = self.config_entry
        collected = self._user_input
        current_host = str(entry.data.get(CONF_HOST, "")).strip()
        current_port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
        new_host = collected.pop(CONF_HOST, current_host)
        new_name = collected.pop(CONF_NAME, entry.title)

        options = dict(entry.options)
        options.update(collected)
        # Drop the sub-settings of features that were switched off
        if not collected.get(CONF_THERMOSTAT_ENABLED):
            for key in THERMOSTAT_KEYS:
                options.pop(key, None)
        if not collected.get(CONF_DHW_SCHEDULE_ENABLED):
            for key in DHW_KEYS:
                options.pop(key, None)

        update: dict[str, Any] = {"options": options}
        data = dict(entry.data)
        if new_host != current_host:
            data[CONF_HOST] = new_host
            data[CONF_PORT] = current_port
            update["unique_id"] = _unique_id(new_host, current_port)
        if new_name != (entry.data.get(CONF_NAME) or entry.title):
            data[CONF_NAME] = new_name
            update["title"] = new_name
        update["data"] = data
        self.hass.config_entries.async_update_entry(entry, **update)
        return self.async_create_entry(title="", data=options)
