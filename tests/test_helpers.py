"""Tests for the Qube Heat Pump helper utilities."""

from __future__ import annotations

import pytest

from custom_components.qube_heatpump.entity_defs import EntityDef
from custom_components.qube_heatpump.helpers import is_alarm_entity


@pytest.mark.parametrize(
    ("platform", "name", "vendor_id", "expected"),
    [
        # alrm_flw-style key: starts with "al", no "alarm" substring, neutral name
        ("binary_sensor", "Flow switch", "alrm_flw", True),
        # name carries "alarm" regardless of the vendor_id
        ("binary_sensor", "Some Alarm Sensor", "neutral", True),
        # neither the name nor the vendor_id hints at an alarm
        ("binary_sensor", "Test", "neutral", False),
        # other platforms are never alarm entities, even with an alarm-like name
        ("sensor", "Alarm Test", "al_test", False),
    ],
    ids=["vendor_id_prefix", "name_contains_alarm", "neutral", "wrong_platform"],
)
def test_is_alarm_entity(
    platform: str, name: str, vendor_id: str, expected: bool
) -> None:
    """The predicate matches binary sensors by vendor_id prefix or by name."""
    ent = EntityDef(platform=platform, name=name, address=100, vendor_id=vendor_id)
    assert is_alarm_entity(ent) is expected
