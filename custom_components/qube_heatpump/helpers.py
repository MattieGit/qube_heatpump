"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity_defs import EntityDef


def entity_data_key(ent: EntityDef) -> str:
    """Key under which the coordinator stores this entity's value."""
    if ent.unique_id:
        return ent.unique_id
    return f"{ent.platform}_{ent.input_type or ent.write_type}_{ent.address}"


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
