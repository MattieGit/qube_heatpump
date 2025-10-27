from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
import struct
import logging
import inspect
import asyncio
import socket
import ipaddress

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.core import HomeAssistant


@dataclass
class EntityDef:
    platform: str
    name: str
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


class WPQubeHub:
    def __init__(self, hass: HomeAssistant, host: str, port: int, unit_id: int = 1, label: str | None = None) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._unit = unit_id
        self._label = label or "qube1"
        self._client: Optional[AsyncModbusTcpClient] = None
        self.entities: List[EntityDef] = []
        # Backoff/timeout controls
        self._connect_backoff_s: float = 0.0
        self._connect_backoff_max_s: float = 60.0
        self._next_connect_ok_at: float = 0.0
        self._io_timeout_s: float = 3.0
        # Error counters
        self._err_connect: int = 0
        self._err_read: int = 0
        self._resolved_ip: str | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def unit(self) -> int:
        return self._unit

    @property
    def label(self) -> str:
        return self._label

    @property
    def resolved_ip(self) -> str | None:
        return self._resolved_ip

    async def async_resolve_ip(self) -> None:
        """Resolve the host to a concrete IP address for diagnostics."""
        try:
            self._resolved_ip = str(ipaddress.ip_address(self._host))
            return
        except Exception:
            pass

        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                self._host,
                None,
                type=socket.SOCK_STREAM,
            )
        except Exception:
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
        now = asyncio.get_running_loop().time()
        if now < self._next_connect_ok_at:
            raise ModbusException("Backoff active; skipping connect attempt")
        if self._client is None:
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
        connected = bool(getattr(self._client, "connected", False))
        if not connected:
            try:
                ok = await asyncio.wait_for(self._client.connect(), timeout=self._io_timeout_s)
            except Exception as exc:
                # Increase backoff
                self._connect_backoff_s = min(self._connect_backoff_max_s, (self._connect_backoff_s or 1.0) * 2)
                self._next_connect_ok_at = now + self._connect_backoff_s
                self._err_connect += 1
                raise ModbusException(f"Failed to connect: {exc}")
            if ok is False:
                self._connect_backoff_s = min(self._connect_backoff_max_s, (self._connect_backoff_s or 1.0) * 2)
                self._next_connect_ok_at = now + self._connect_backoff_s
                self._err_connect += 1
                raise ModbusException("Failed to connect to Modbus TCP server")
            # Reset backoff after success
            self._connect_backoff_s = 0.0
            self._next_connect_ok_at = 0.0

    async def _call(self, method: str, **kwargs):
        if self._client is None:
            raise ModbusException("Client not connected")
        func = getattr(self._client, method)
        # Try with 'slave' then 'unit', finally without either
        try:
            resp = await asyncio.wait_for(func(**{**kwargs, "slave": self._unit}), timeout=self._io_timeout_s)
        except TypeError:
            try:
                resp = await asyncio.wait_for(func(**{**kwargs, "unit": self._unit}), timeout=self._io_timeout_s)
            except TypeError:
                resp = await asyncio.wait_for(func(**kwargs), timeout=self._io_timeout_s)
        # Normalize error checking
        if hasattr(resp, "isError") and resp.isError():
            raise ModbusException(f"Modbus error on {method} with {kwargs}")
        return resp

    async def async_close(self) -> None:
        if self._client is not None:
            try:
                res = self._client.close()
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                # Swallow close errors
                pass
            finally:
                self._client = None

    def set_unit_id(self, unit_id: int) -> None:
        self._unit = int(unit_id)

    @property
    def err_connect(self) -> int:
        return self._err_connect

    @property
    def err_read(self) -> int:
        return self._err_read

    def inc_read_error(self) -> None:
        self._err_read += 1

    async def async_read_value(self, ent: EntityDef) -> Any:
        if self._client is None:
            raise ModbusException("Client not connected")

        if ent.platform == "binary_sensor":
            input_type = (ent.input_type or "discrete_input").lower()
            if input_type in ("discrete_input", "discrete", "discreteinputs", "discreteinput"):
                rr = await self._call("read_discrete_inputs", address=ent.address, count=1)
                return bool(getattr(rr, "bits", [False])[0])
            if input_type in ("coil", "coils"):
                rr = await self._call("read_coils", address=ent.address, count=1)
                return bool(getattr(rr, "bits", [False])[0])
            if input_type in ("holding", "holding_register", "register", "holdingregister"):
                rr = await self._call("read_holding_registers", address=ent.address, count=1)
                regs = getattr(rr, "registers", None)
                if not regs:
                    return None
                return bool(int(regs[0]) & 0xFFFF)
            if input_type in ("input", "input_register", "inputregister"):
                rr = await self._call("read_input_registers", address=ent.address, count=1)
                regs = getattr(rr, "registers", None)
                if not regs:
                    return None
                return bool(int(regs[0]) & 0xFFFF)
            rr = await self._call("read_discrete_inputs", address=ent.address, count=1)
            return bool(getattr(rr, "bits", [False])[0])

        if ent.platform == "switch":
            write_type = (ent.write_type or "coil").lower()
            if write_type in ("coil", "coils"):
                rr = await self._call("read_coils", address=ent.address, count=1)
                return bool(getattr(rr, "bits", [False])[0])

            if write_type in ("holding", "holding_register", "register", "holdingregister"):
                data_type = (ent.data_type or "uint16").lower()
                count = 2 if data_type == "float32" else 1
                try:
                    rr = await self._call("read_holding_registers", address=ent.address, count=count)
                except ModbusException:
                    fallback_addr = ent.address - 1
                    if fallback_addr < 0:
                        raise
                    logging.getLogger(__name__).info(
                        "Modbus holding read failed @ %s, retrying @ %s (fallback)",
                        ent.address,
                        fallback_addr,
                    )
                    rr = await self._call("read_holding_registers", address=fallback_addr, count=count)

                regs = getattr(rr, "registers", None)
                if not regs:
                    return None
                try:
                    if data_type == "float32" and len(regs) >= 2:
                        raw = struct.pack(">HH", int(regs[0]) & 0xFFFF, int(regs[1]) & 0xFFFF)
                        val = struct.unpack(">f", raw)[0]
                    else:
                        val = int(regs[0])
                    return bool(val)
                except Exception:
                    return None

            raise ModbusException(f"Unsupported switch write_type: {write_type}")

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

        # Clamp to minimum value if configured
        if ent.min_value is not None:
            try:
                if float(val) < float(ent.min_value):
                    val = float(ent.min_value)
            except Exception:
                pass

        if ent.precision is not None:
            try:
                p = int(ent.precision)
                f = float(val)
                if p == 0:
                    val = int(round(f))
                else:
                    val = round(f, p)
            except Exception:
                pass

        return val

    async def async_write_register(self, address: int, value: float, data_type: str = "uint16") -> None:
        if self._client is None:
            raise ModbusException("Client not connected")

        data_type = (data_type or "uint16").lower()

        async def _write(addr: int) -> None:
            if data_type in ("float32", "float"):
                raw = struct.pack(">f", float(value))
                hi = int.from_bytes(raw[:2], "big")
                lo = int.from_bytes(raw[2:], "big")
                await self._call("write_registers", address=addr, values=[hi & 0xFFFF, lo & 0xFFFF])
                return

            if data_type in ("int16", "int"):
                int_val = int(round(float(value)))
                if not -32768 <= int_val <= 32767:
                    raise ModbusException("int16 value out of range")
                if int_val < 0:
                    int_val = (1 << 16) + int_val
                await self._call("write_register", address=addr, value=int_val & 0xFFFF)
                return

            if data_type in ("uint16", "uint"):
                int_val = int(round(float(value)))
                if not 0 <= int_val <= 0xFFFF:
                    raise ModbusException("uint16 value out of range")
                await self._call("write_register", address=addr, value=int_val & 0xFFFF)
                return

            raise ModbusException(f"Unsupported data_type for register write: {data_type}")

        try:
            await _write(address)
            return
        except ModbusException:
            fallback_addr = address - 1
            if fallback_addr < 0:
                raise
            logging.getLogger(__name__).info(
                "Modbus register write failed @ %s, retrying @ %s (fallback)", address, fallback_addr
            )
            await _write(fallback_addr)

    async def async_write_switch(self, ent: EntityDef, on: bool) -> None:
        if self._client is None:
            raise ModbusException("Client not connected")
        value = 1 if on else 0
        write_type = (ent.write_type or "coil").lower()
        try:
            if write_type in ("coil", "coils"):
                await self._call("write_coil", address=ent.address, value=value)
                return
            if write_type in ("holding", "holding_register", "register", "holdingregister"):
                await self.async_write_register(ent.address, value, ent.data_type or "uint16")
                return
        except ModbusException:
            fallback_addr = ent.address - 1
            if fallback_addr >= 0:
                logging.getLogger(__name__).info(
                    "Modbus write failed @ %s, retrying @ %s (fallback)", ent.address, fallback_addr
                )
                if write_type in ("coil", "coils"):
                    await self._call("write_coil", address=fallback_addr, value=value)
                    return
                if write_type in ("holding", "holding_register", "register", "holdingregister"):
                    await self.async_write_register(fallback_addr, value, ent.data_type or "uint16")
                    return
            raise

        raise ModbusException(f"Unsupported switch write_type: {write_type}")
