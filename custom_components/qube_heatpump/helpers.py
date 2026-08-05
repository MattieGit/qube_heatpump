"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hub import EntityDef


def slugify(text: str) -> str:
    """Make text safe for use as an entity ID component.

    Converts text to lowercase alphanumeric with underscores.
    """
    return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()


def is_alarm_entity(ent: EntityDef) -> bool:
    """Check if an entity definition is an alarm binary sensor."""
    if ent.platform != "binary_sensor":
        return False
    if "alarm" in (ent.name or "").lower():
        return True
    return (ent.vendor_id or "").lower().startswith("al")
