"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .entity_defs import EntityDef
    from .hub import QubeHub

# Library keys of the backup heater step outputs and the three-way valve
HEATER_STEP_KEYS = (
    "dout_heaterstep1_val",
    "dout_heaterstep2_val",
    "dout_heaterstep3_val",
)
THREEWAY_VALVE_KEY = "dout_threewayvlv_val"
# Where the heater's heat goes, by three-way valve position
HEATER_MODES = ("ch", "dhw")


def entity_data_key(ent: EntityDef) -> str:
    """Key under which the coordinator stores this entity's value."""
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


def has_heater_inputs(hub: QubeHub) -> bool:
    """Return True when the hub reads every heater step output and the valve."""
    vendor_ids = {ent.vendor_id for ent in hub.entities}
    return all(key in vendor_ids for key in (*HEATER_STEP_KEYS, THREEWAY_VALVE_KEY))


def active_heater_steps(data: Mapping[str, Any] | None) -> int | None:
    """Number of backup heater steps that are on, or None if a reading is missing."""
    if not data:
        return None
    values = [data.get(key) for key in HEATER_STEP_KEYS]
    if any(value is None for value in values):
        return None
    return sum(bool(value) for value in values)


def threeway_valve_mode(data: Mapping[str, Any] | None) -> str | None:
    """Return "dhw" or "ch" for the three-way valve, or None if unknown."""
    if not data:
        return None
    value = data.get(THREEWAY_VALVE_KEY)
    if value is None:
        return None
    return "dhw" if value else "ch"


def is_alarm_entity(ent: EntityDef) -> bool:
    """Check if an entity definition is an alarm binary sensor."""
    if ent.platform != "binary_sensor":
        return False
    if "alarm" in (ent.name or "").lower():
        return True
    return (ent.vendor_id or "").lower().startswith("al")


async def async_resolve_host(host: str) -> str | None:
    """Resolve a host name or IP literal to a canonical IP address.

    Returns None when the host is empty or cannot be resolved. IPv4-mapped
    IPv6 addresses are unwrapped so the same device always yields the same
    address regardless of the resolver's address family.
    """
    if not host:
        return None
    with contextlib.suppress(ValueError):
        return str(ipaddress.ip_address(host))

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, type=socket.SOCK_STREAM
        )
    except OSError:
        return None

    for family, _, _, _, sockaddr in infos:
        if not sockaddr:
            continue
        addr = sockaddr[0]
        if not isinstance(addr, str):
            continue
        if family == socket.AF_INET6:
            addr = addr.removeprefix("::ffff:")
        return addr
    return None
