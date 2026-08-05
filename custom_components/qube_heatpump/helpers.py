"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

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
