"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hub import EntityDef


def slugify(text: str) -> str:
    """Make text safe for use as an entity ID component.

    Converts text to lowercase alphanumeric with underscores.
    """
    return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()


def suggest_object_id(
    ent: EntityDef,
    label: str,
) -> str | None:
    """Generate a suggested object_id for an entity.

    Always uses the pattern: {label}_{vendor_id}
    Example: qube_cop_calc, qube_temp_supply

    Args:
        ent: Entity definition with vendor_id
        label: Hub label (e.g., "qube", "qube1")

    Returns:
        Suggested object ID slug, or None if no vendor_id
    """
    vendor_id = getattr(ent, "vendor_id", None)
    if not vendor_id:
        return None
    return slugify(f"{label}_{vendor_id}")


def derive_label_from_title(title: str) -> str:
    """Derive a label from an entry title for entity ID prefixing.

    Args:
        title: Config entry title (e.g., "Qube Heat Pump (192.168.1.50)")

    Returns:
        Slugified label (e.g., "qube_192_168_1_50" or "qube1")
    """
    # Extract content from parentheses if present
    match = re.search(r"\(([^)]+)\)", title)
    if match:
        inner = match.group(1)
        return slugify(inner)
    # Fallback to slugified title
    return slugify(title) or "qube1"
