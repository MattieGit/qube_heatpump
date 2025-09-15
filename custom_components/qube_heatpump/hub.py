from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
import struct
import logging
import inspect

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.core import HomeAssistant


@dataclass
class EntityDef:
    platform: str
    name: str
    address: int
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


class WPQubeHub:
    def __init__(self, hass: HomeAssistant, host: str, port: int, unit_id: int = 1) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._unit = unit_id
        self._client: Optional[AsyncModbusTcpClient] = None
        self.entities: List[EntityDef] = []

    @property
    def host(self) -> str:
        return self._host

    async def async_connect(self) -> None:
        if self._client is None:
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
        try:
            connected = getattr(self._client, "connected", False)
        except Exception:
            connected = False
        if not connected:
            ok = await self._client.connect()
            if ok is False:
                raise ModbusException("Failed to connect to Modbus TCP server")

    async def _call(self, method: str, **kwargs):
        if self._client is None:
            raise ModbusException("Client not connected")
        func = getattr(self._client, method)
        sig = None
        try:
            sig = inspect.signature(func)
        except Exception:
            sig = None
        # Inject unit/slave kwarg depending on signature
        if sig and "slave" in sig.parameters:
            kwargs.setdefault("slave", self._unit)
        else:
            kwargs.setdefault("unit", self._unit)
        resp = await func(**kwargs)
        # Normalize error checking
        if hasattr(resp, "isError") and resp.isError():
            raise ModbusException(f"Modbus error on {method} with {kwargs}")
        return resp

    async def async_close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def async_read_value(self, ent: EntityDef) -> Any:
        if self._client is None:
            raise ModbusException("Client not connected")

        if ent.platform == "binary_sensor":
            # Expect discrete inputs
            rr = await self._call("read_discrete_inputs", address=ent.address, count=1)
            return bool(getattr(rr, "bits", [False])[0])

        if ent.platform == "switch":
            # Read coil state to reflect actual device state
            rr = await self._call("read_coils", address=ent.address, count=1)
            return bool(getattr(rr, "bits", [False])[0])

        # sensor
        count = 1
        if ent.data_type in ("float32", "uint32", "int32"):
            count = 2

        try:
            if ent.input_type == "input":
                rr = await self._call("read_input_registers", address=ent.address, count=count)
            else:
                # default to holding
                rr = await self._call("read_holding_registers", address=ent.address, count=count)
        except ModbusException:
            # Some devices/YAMLs use 1-based addresses; try address-1 as fallback
            fallback_addr = ent.address - 1
            if fallback_addr < 0:
                raise
            logging.getLogger(__name__).info(
                "Modbus read failed @ %s, retrying @ %s (fallback)", ent.address, fallback_addr
            )
            if ent.input_type == "input":
                rr = await self._call("read_input_registers", address=fallback_addr, count=count)
            else:
                rr = await self._call("read_holding_registers", address=fallback_addr, count=count)

        regs = getattr(rr, "registers", None)
        if regs is None:
            raise ModbusException("No registers returned")

        # All decoding assumes big-endian word and byte order.
        if ent.data_type == "float32":
            raw = struct.pack(">HH", int(regs[0]) & 0xFFFF, int(regs[1]) & 0xFFFF)
            val = struct.unpack(">f", raw)[0]
        elif ent.data_type == "int16":
            v = int(regs[0]) & 0xFFFF
            val = v - 0x10000 if v & 0x8000 else v
        elif ent.data_type == "uint16":
            val = int(regs[0]) & 0xFFFF
        elif ent.data_type == "uint32":
            val = ((int(regs[0]) & 0xFFFF) << 16) | (int(regs[1]) & 0xFFFF)
        elif ent.data_type == "int32":
            u = ((int(regs[0]) & 0xFFFF) << 16) | (int(regs[1]) & 0xFFFF)
            val = u - 0x1_0000_0000 if u & 0x8000_0000 else u
        else:
            # Fallback to first register as unsigned 16-bit
            val = int(regs[0]) & 0xFFFF

        # Apply scale/offset as value = value * scale + offset
        if ent.scale is not None:
            try:
                val = float(val) * float(ent.scale)
            except Exception:
                pass
        if ent.offset is not None:
            try:
                val = float(val) + float(ent.offset)
            except Exception:
                pass

        if ent.precision is not None:
            try:
                val = round(float(val), int(ent.precision))
            except Exception:
                pass

        return val

    async def async_write_switch(self, ent: EntityDef, on: bool) -> None:
        if self._client is None:
            raise ModbusException("Client not connected")
        # Only coil writes are defined in the YAML
        await self._call("write_coil", address=ent.address, value=1 if on else 0)
