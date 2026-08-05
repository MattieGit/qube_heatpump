"""Helper utilities for Qube Heat Pump integration."""

from __future__ import annotations


def slugify(text: str) -> str:
    """Make text safe for use as an entity ID component.

    Converts text to lowercase alphanumeric with underscores.
    """
    return "".join(ch if ch.isalnum() else "_" for ch in str(text)).strip("_").lower()
