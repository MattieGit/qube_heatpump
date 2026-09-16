"""Hub for Qube Heat Pump communication using python-qube-heatpump library."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any

from python_qube_heatpump import BINARY_SENSORS, SENSORS, SWITCHES, QubeClient

from .entity_defs import EntityDef, _library_to_ha_entity
from .helpers import async_resolve_host, entity_data_key

_LOGGER = logging.getLogger(__name__)


class QubeHub:
    """Qube Heat Pump Hub wrapping the library's QubeClient."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int = 1,
        device_name: str | None = None,
    ) -> None:
        """Initialize the hub and its (not yet connected) client."""
        self._host = host
        self._port = port
        self._unit = unit_id
        self._device_name = device_name or "Qube Heat Pump"
        self.client = QubeClient(host, port, unit_id)
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
        self.entities = [
            _library_to_ha_entity(lib_ent)
            for lib_ent in (
                *BINARY_SENSORS.values(),
                *SENSORS.values(),
                *SWITCHES.values(),
            )
        ]
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
        """Return label derived from device name (used in entity IDs)."""
        return self._label

    @property
    def device_name(self) -> str:
        """Return device name for DeviceInfo."""
        return self._device_name

    @property
    def resolved_ip(self) -> str | None:
        """Return resolved IP address."""
        return self._resolved_ip

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

    async def async_resolve_ip(self) -> None:
        """Resolve the host to a concrete IP address for diagnostics."""
        self._resolved_ip = await async_resolve_host(self._host)

    async def async_connect(self) -> None:
        """Connect to the Modbus server via the library client.

        Raises ConnectionError when the device cannot be reached.
        """
        if self.client.is_connected:
            return
        try:
            connected = await self.client.connect()
        except OSError as exc:
            self._err_connect += 1
            raise ConnectionError(f"Failed to connect: {exc}") from exc
        if not connected:
            self._err_connect += 1
            raise ConnectionError("Failed to connect to Modbus TCP server")

    async def async_close(self) -> None:
        """Close the connection."""
        with contextlib.suppress(OSError):
            await self.client.close()

    async def async_get_software_version(self) -> str | None:
        """Get the firmware software version from the device (None on failure)."""
        return await self.client.async_get_software_version()

    async def async_get_all_entities(self) -> dict[str, Any]:
        """Read all entity values in a few batched Modbus block reads."""
        return await self.client.get_all_entities()

    async def async_write_switch(self, ent: EntityDef, on: bool) -> None:
        """Write a switch (coil) state via the library client."""
        key = entity_data_key(ent)
        if not await self.client.write_switch(key, on):
            raise ConnectionError(f"Failed to write switch {key}")

    async def async_write_setpoint(self, ent: EntityDef, value: float) -> None:
        """Write a setpoint (holding register) value via the library client."""
        key = entity_data_key(ent)
        if not await self.client.write_setpoint(key, value):
            raise ConnectionError(f"Failed to write setpoint {key}")

    async def async_write_register(self, address: int, value: float) -> None:
        """Write a value to the writable entity registered at ``address``.

        This is not a raw register write: the address must belong to a known
        writable entity so the library can apply the right encoding. Coils
        only accept 0 or 1. Raises ValueError for an unknown address or an
        invalid coil value and ConnectionError when the device rejects the
        write.
        """
        for ent in self.entities:
            if ent.address != address or not ent.writable:
                continue
            if ent.platform == "switch":
                if value not in (0, 1):
                    raise ValueError(
                        f"Coil at address {address} only accepts 0 or 1, got {value}"
                    )
                await self.async_write_switch(ent, bool(value))
                return
            await self.async_write_setpoint(ent, value)
            return

        raise ValueError(f"No writable entity found at address {address}")
