"""Hub for Qube Heat Pump communication using python-qube-heatpump library."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import re
import socket
from typing import TYPE_CHECKING, Any

from python_qube_heatpump import BINARY_SENSORS, SENSORS, SWITCHES, QubeClient

from .entity_defs import EntityDef, _library_to_ha_entity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class QubeHub:
    """Qube Heat Pump Hub wrapping the library's QubeClient."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        entry_id: str,
        unit_id: int = 1,
        device_name: str | None = None,
    ) -> None:
        """Initialize the hub."""
        self._hass = hass
        self._host = host
        self._port = port
        self.entry_id = entry_id
        self._unit = unit_id
        self._device_name = device_name or "Qube Heat Pump"
        self._client: QubeClient | None = None
        self.entities: list[EntityDef] = []
        # Error counters
        self._err_connect: int = 0
        self._err_read: int = 0
        self._resolved_ip: str | None = None
        # Slugify the device name once to create a stable label
        slug = re.sub(r"[^a-z0-9]+", "_", self._device_name.lower())
        self._label = slug.strip("_") or "qube"

    def load_library_entities(self) -> None:
        """Load all entity definitions from the library."""
        self.entities = []

        # Load binary sensors
        for lib_ent in BINARY_SENSORS.values():
            self.entities.append(_library_to_ha_entity(lib_ent))

        # Load sensors
        for lib_ent in SENSORS.values():
            self.entities.append(_library_to_ha_entity(lib_ent))

        # Load switches
        for lib_ent in SWITCHES.values():
            self.entities.append(_library_to_ha_entity(lib_ent))

        _LOGGER.debug(
            "Loaded %d entities from library (%d binary_sensor, %d sensor, %d switch)",
            len(self.entities),
            len(BINARY_SENSORS),
            len(SENSORS),
            len(SWITCHES),
        )

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    @property
    def port(self) -> int:
        """Return port."""
        return self._port

    @property
    def unit(self) -> int:
        """Return unit ID."""
        return self._unit

    @property
    def label(self) -> str:
        """Return label derived from device name (for backwards compatibility)."""
        return self._label

    @property
    def device_name(self) -> str:
        """Return device name for DeviceInfo."""
        return self._device_name

    @property
    def resolved_ip(self) -> str | None:
        """Return resolved IP address."""
        return self._resolved_ip

    async def async_resolve_ip(self) -> None:
        """Resolve the host to a concrete IP address for diagnostics."""
        with contextlib.suppress(ValueError):
            self._resolved_ip = str(ipaddress.ip_address(self._host))
            return

        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                self._host,
                None,
                type=socket.SOCK_STREAM,
            )
        except OSError:
            self._resolved_ip = None
            return

        for family, _, _, _, sockaddr in infos:
            if not sockaddr:
                continue
            addr = sockaddr[0]
            if not isinstance(addr, str):
                continue
            if family == socket.AF_INET6 and addr.startswith("::ffff:"):
                addr = addr.removeprefix("::ffff:")
            self._resolved_ip = addr
            return

        self._resolved_ip = None

    async def async_connect(self) -> None:
        """Connect to the Modbus server via the library client."""
        if self._client is None:
            self._client = QubeClient(self._host, self._port, self._unit)

        if not self._client.is_connected:
            try:
                connected = await self._client.connect()
            except Exception as exc:
                self._err_connect += 1
                raise ConnectionError(f"Failed to connect: {exc}") from exc

            if not connected:
                self._err_connect += 1
                raise ConnectionError("Failed to connect to Modbus TCP server")

    async def async_close(self) -> None:
        """Close the connection."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()
            self._client = None

    @property
    def client(self) -> QubeClient | None:
        """Return the underlying QubeClient instance."""
        return self._client

    @property
    def err_connect(self) -> int:
        """Return connect error count."""
        return self._err_connect

    @property
    def err_read(self) -> int:
        """Return read error count."""
        return self._err_read

    def inc_read_error(self) -> None:
        """Increment read error count."""
        self._err_read += 1

    async def async_get_software_version(self) -> str | None:
        """Get the firmware software version from the device."""
        if self._client is None:
            return None
        return await self._client.async_get_software_version()

    async def async_get_all_entities(self) -> dict[str, Any]:
        """Get all entity values from the library client."""
        if self._client is None:
            raise ConnectionError("Client not connected")

        return await self._client.get_all_entities()

    async def async_write_switch(self, ent: EntityDef, on: bool) -> None:
        """Write a switch state via the library client."""
        if self._client is None:
            raise ConnectionError("Client not connected")

        # Use library write method
        if ent.unique_id:
            success = await self._client.write_switch(ent.unique_id, on)
            if not success:
                raise ConnectionError(f"Failed to write switch {ent.unique_id}")
            return

        raise ConnectionError(
            f"No unique_id for switch entity at address {ent.address}"
        )

    async def async_write_setpoint(self, ent: EntityDef, value: float) -> None:
        """Write a setpoint value via the library client."""
        if self._client is None:
            raise ConnectionError("Client not connected")

        # Use library write method
        if ent.unique_id:
            success = await self._client.write_setpoint(ent.unique_id, value)
            if not success:
                raise ConnectionError(f"Failed to write setpoint {ent.unique_id}")
            return

        raise ConnectionError(
            f"No unique_id for setpoint entity at address {ent.address}"
        )

    async def async_write_register(self, address: int, value: float) -> None:
        """Write a value to a register via the library client.

        This is a low-level method for the write_register service.
        """
        if self._client is None:
            raise ConnectionError("Client not connected")

        # Find the entity with this address to use library write methods
        for ent in self.entities:
            if ent.address == address and ent.writable:
                if ent.platform == "switch":
                    await self.async_write_switch(ent, bool(value))
                    return
                await self.async_write_setpoint(ent, value)
                return

        # No matching entity found - this would require direct pymodbus access
        # which we're avoiding. Raise an error instead.
        raise ConnectionError(
            f"No writable entity found at address {address}. "
            "Use entity-specific methods instead."
        )
