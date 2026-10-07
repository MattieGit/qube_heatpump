"""Config flow for Qube Heat Pump integration."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import TYPE_CHECKING, Any

from python_qube_heatpump import QubeClient, async_get_device_info, parse_device_info
import voluptuous as vol

from homeassistant.components import zeroconf
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
    TextSelector,
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
from .hub import MDNS_LOOKUP_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

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
    """Host-based unique id, used until the controller's mDNS uuid is known."""
    return f"{DOMAIN}-{host}-{port}"


def _is_controller_uuid(unique_id: str | None) -> bool:
    """Return True when the unique id is the controller's mDNS uuid."""
    return unique_id is not None and not unique_id.startswith(f"{DOMAIN}-")


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


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

    Returns an error key (``duplicate_ip``, ``cannot_connect`` or
    ``not_qube_device``) or None when the host is unique among the other
    entries and answers like a Qube controller over Modbus.
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

    client = QubeClient(host, port)
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT):
            if not await client.connect():
                return "cannot_connect"
            # Any readable software-version register counts, including 0
            if not await client.async_verify_device():
                return "not_qube_device"
    except (OSError, TimeoutError):
        return "cannot_connect"
    finally:
        await client.close()
    return None


async def _async_check_host(
    hass: HomeAssistant, host: str, port: int, *, entry: ConfigEntry | None = None
) -> tuple[str | None, str]:
    """Validate a host and work out the unique id its entry gets.

    Returns an error key (or None) and the unique id: the controller's mDNS
    uuid when it answers, otherwise the entry's existing uuid, otherwise a
    host-based id. An entry keyed on a uuid refuses a different controller.
    """
    if error := await _async_validate_host(
        hass, host, port, skip_entry_id=entry.entry_id if entry else None
    ):
        return error, ""

    aiozc = await zeroconf.async_get_async_instance(hass)
    device = await async_get_device_info(host, aiozc, timeout=MDNS_LOOKUP_TIMEOUT)
    current = entry.unique_id if entry else None
    if _is_controller_uuid(current):
        if device is not None and device.uuid != current:
            return "different_heat_pump", ""
        return None, str(current)
    return None, device.uuid if device else _unique_id(host, port)


class QubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qube Heat Pump."""

    VERSION = 2

    _discovered_host: str

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

            error, unique_id = await _async_check_host(self.hass, host, port)
            if error:
                errors[CONF_HOST] = error
            else:
                await self.async_set_unique_id(unique_id)
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
                host_field: TextSelector(),
                vol.Optional(CONF_NAME, default=self._default_name()): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"docs_url": DOCS_URL},
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Qube discovered through its mDNS advertisement."""
        if (device := parse_device_info(discovery_info.properties)) is None:
            return self.async_abort(reason="not_qube_device")

        host = discovery_info.host
        await self.async_set_unique_id(device.uuid)
        # Follow a new DHCP address, but keep a host name the user entered
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, device.uuid
        )
        updates = (
            {CONF_HOST: host}
            if entry is not None and _is_ip_address(entry.data.get(CONF_HOST, ""))
            else None
        )
        # The entry's update listener reloads it after a data change
        self._abort_if_unique_id_configured(updates=updates, reload_on_update=False)

        # Entries set up before mDNS was seen still have a host-based id; they
        # adopt the uuid on their next start
        if await _async_find_conflicting_entry(
            self._async_current_entries(include_ignore=False), host
        ):
            return self.async_abort(reason="already_configured")

        self._discovered_host = host
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered Qube and choose its device name."""
        errors: dict[str, str] = {}
        host = self._discovered_host

        if user_input is not None:
            name = user_input.get(CONF_NAME, "").strip() or self._default_name()
            port = DEFAULT_PORT
            error, _ = await _async_check_host(self.hass, host, port)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_NAME: name},
                )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema(
                {vol.Optional(CONF_NAME, default=self._default_name()): str}
            ),
            description_placeholders={"host": host},
            errors=errors,
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
        error, unique_id = await _async_check_host(self.hass, host, port, entry=entry)
        if error:
            return self._show_reconfigure_form(entry, {CONF_HOST: error})
        for other in self._async_current_entries():
            if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                return self.async_abort(reason="already_configured")

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
                vol.Required(
                    CONF_HOST, default=entry.data.get(CONF_HOST)
                ): TextSelector(),
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
        self._unique_id: str | None = None

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
            elif host_changed:
                error, self._unique_id = await _async_check_host(
                    self.hass, new_host, current_port, entry=entry
                )
                if error:
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
                vol.Required(CONF_HOST, default=current_host): TextSelector(),
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
            update["unique_id"] = self._unique_id or _unique_id(new_host, current_port)
        if new_name != (entry.data.get(CONF_NAME) or entry.title):
            data[CONF_NAME] = new_name
            update["title"] = new_name
        update["data"] = data
        self.hass.config_entries.async_update_entry(entry, **update)
        return self.async_create_entry(title="", data=options)
