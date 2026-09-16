"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry

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


def get_device_by_identifier(
    registry: DeviceRegistry, identifier: tuple[str, str], entry_id: str
) -> DeviceEntry | None:
    """Look up a device by one identifier, scoped to a config entry.

    Home Assistant 2026.7 added ``async_get_device_by_identifier`` and
    deprecated ``async_get_device`` (removal planned for 2027.8). Older cores
    still supported by this integration only have the deprecated form.
    """
    lookup = getattr(registry, "async_get_device_by_identifier", None)
    if lookup is not None:
        return cast("DeviceEntry | None", lookup(identifier, entry_id))
    return registry.async_get_device(identifiers={identifier})
