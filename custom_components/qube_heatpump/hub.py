"""Hub for Qube Heat Pump communication using python-qube-heatpump library."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import ipaddress
import logging
import socket
from typing import TYPE_CHECKING, Any

from python_qube_heatpump import (
    BINARY_SENSORS,
    SENSORS,
    SWITCHES,
    EntityDef as LibraryEntityDef,
    QubeClient,
)
from python_qube_heatpump.entities.base import InputType, Platform

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Make text safe for use as an ID."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()


@dataclass
class EntityDef:
    """Definition of a Qube entity for Home Assistant.

    This wraps the library's EntityDef with HA-specific metadata.
    """

    platform: str
    name: str | None
    address: int
    vendor_id: str | None = None
    input_type: str | None = None
    write_type: str | None = None
    data_type: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    precision: int | None = None
    unique_id: str | None = None
    offset: float | None = None
    scale: float | None = None
    min_value: float | None = None
    translation_key: str | None = None
    writable: bool = False
    # Reference to the library's entity definition
    _library_entity: LibraryEntityDef | None = None


def _derive_device_class(unit: str | None, key: str) -> str | None:
    """Derive Home Assistant device_class from unit of measurement."""
    if not unit:
        # Check key for status/enum entities
        if "status" in key.lower() or key == "unitstatus":
            return "enum"
        return None

    unit_lower = unit.lower()
    if unit_lower in ("°c", "c"):
        return "temperature"
    if unit_lower == "w":
        return "power"
    if unit_lower == "kwh":
        return "energy"
    if unit_lower == "%":
        return "power_factor"
    if unit_lower == "hz":
        return "frequency"
    if unit_lower == "bar":
        return "pressure"
    if unit_lower in ("h", "hours"):
        return "duration"
    return None


def _derive_state_class(unit: str | None, device_class: str | None, key: str) -> str | None:
    """Derive Home Assistant state_class from unit and device_class."""
    if device_class == "enum":
        return None

    # Energy sensors are typically total_increasing
    if device_class == "energy" or (unit and unit.lower() == "kwh"):
        return "total_increasing"

    # Working hours and accumulated values are total_increasing
    key_lower = key.lower()
    if "workinghours" in key_lower or "acumulated" in key_lower:
        return "total_increasing"

    # Most other numeric sensors are measurements
    if unit:
        return "measurement"

    return None


def _derive_precision(unit: str | None, data_type: str | None) -> int | None:
    """Derive suggested display precision from unit and data type."""
    if not unit:
        return None

    unit_lower = unit.lower()
    if unit_lower in ("°c", "c"):
        return 1
    if unit_lower == "kwh":
        return 2
    if unit_lower == "w":
        return 0
    if unit_lower == "%":
        return 1
    if unit_lower == "bar":
        return 2

    # Float32 types often need decimal precision
    if data_type == "float32":
        return 2

    return None


def _library_to_ha_entity(lib_ent: LibraryEntityDef) -> EntityDef:
    """Convert a library EntityDef to an HA EntityDef."""
    # Map platform enum to string
    platform_map = {
        Platform.SENSOR: "sensor",
        Platform.BINARY_SENSOR: "binary_sensor",
        Platform.SWITCH: "switch",
    }

    # Map input type enum to string
    input_type_map = {
        InputType.COIL: "coil",
        InputType.DISCRETE_INPUT: "discrete_input",
        InputType.INPUT_REGISTER: "input",
        InputType.HOLDING_REGISTER: "holding",
    }

    # Determine write_type for switches
    write_type = None
    if lib_ent.platform == Platform.SWITCH:
        write_type = input_type_map.get(lib_ent.input_type, "coil")

    # Derive HA-specific metadata
    data_type_str = lib_ent.data_type.value if lib_ent.data_type else None
    device_class = _derive_device_class(lib_ent.unit, lib_ent.key)
    state_class = _derive_state_class(lib_ent.unit, device_class, lib_ent.key)
    precision = _derive_precision(lib_ent.unit, data_type_str)

    return EntityDef(
        platform=platform_map.get(lib_ent.platform, "sensor"),
        name=lib_ent.name,
        address=lib_ent.address,
        vendor_id=lib_ent.key,
        input_type=input_type_map.get(lib_ent.input_type) if lib_ent.input_type else None,
        write_type=write_type,
        data_type=data_type_str,
        unit_of_measurement=lib_ent.unit,
        device_class=device_class,
        state_class=state_class,
        precision=precision,
        offset=lib_ent.offset,
        scale=lib_ent.scale,
        unique_id=lib_ent.key,
        translation_key=lib_ent.key,
        writable=lib_ent.writable,
        _library_entity=lib_ent,
    )


class QubeHub:
    """Qube Heat Pump Hub wrapping the library's QubeClient."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        entry_id: str,
        unit_id: int = 1,
        label: str | None = None,
    ) -> None:
        """Initialize the hub."""
        self._hass = hass
        self._host = host
        self._port = port
        self.entry_id = entry_id
        self._unit = unit_id
        self._label = label or "qube1"
        self._client: QubeClient | None = None
        self.entities: list[EntityDef] = []
        # Error counters
        self._err_connect: int = 0
        self._err_read: int = 0
        self._resolved_ip: str | None = None
        self._translations: dict[str, Any] = {}

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

    def set_translations(self, translations: dict[str, Any]) -> None:
        """Set translations for friendly name resolution."""
        self._translations = translations

    def get_friendly_name(self, platform: str, key: str | None) -> str | None:
        """Get friendly name from translations."""
        if not key or not self._translations:
            return None
        with contextlib.suppress(Exception):
            val = (
                self._translations.get("entity", {})
                .get(platform, {})
                .get(key, {})
                .get("name")
            )
            return val if isinstance(val, str) else None
        return None

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
        """Return label."""
        return self._label

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

    def set_unit_id(self, unit_id: int) -> None:
        """Set unit ID."""
        self._unit = int(unit_id)
        if self._client is not None:
            self._client.unit = self._unit

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

    async def async_get_all_entities(self) -> dict[str, Any]:
        """Get all entity values from the library client."""
        if self._client is None:
            raise ConnectionError("Client not connected")

        return await self._client.get_all_entities()

    async def async_read_value(self, ent: EntityDef) -> Any:
        """Read a single entity value via the library client."""
        if self._client is None:
            raise ConnectionError("Client not connected")

        # Use library entity if available
        if ent._library_entity is not None:
            return await self._client.read_entity(ent._library_entity)

        # Fallback: Use key-based reads
        if ent.unique_id:
            if ent.platform == "binary_sensor":
                return await self._client.read_binary_sensor(ent.unique_id)
            if ent.platform == "switch":
                return await self._client.read_switch(ent.unique_id)
            if ent.platform == "sensor":
                return await self._client.read_sensor(ent.unique_id)

        return None

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

        raise ConnectionError(f"No unique_id for switch entity at address {ent.address}")

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

        raise ConnectionError(f"No unique_id for setpoint entity at address {ent.address}")

    async def async_write_register(
        self, address: int, value: float, data_type: str = "uint16"
    ) -> None:
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
