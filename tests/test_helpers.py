"""Tests for the Qube Heat Pump helper utilities."""

from __future__ import annotations

from custom_components.qube_heatpump.helpers import is_alarm_entity
from custom_components.qube_heatpump.hub import EntityDef


class TestIsAlarmEntity:
    """Tests for the is_alarm_entity predicate."""

    def test_matches_vendor_id_starting_with_al(self) -> None:
        """An alrm_flw-style vendor_id (starts with 'al', no 'alarm' substring,
        neutral name) should be classified as an alarm entity.
        """
        ent = EntityDef(
            platform="binary_sensor",
            name="Flow switch",
            address=100,
            vendor_id="alrm_flw",
        )
        assert is_alarm_entity(ent) is True

    def test_matches_name_containing_alarm(self) -> None:
        """An entity whose name contains 'alarm' should match regardless of vendor_id."""
        ent = EntityDef(
            platform="binary_sensor",
            name="Some Alarm Sensor",
            address=101,
            vendor_id="neutral",
        )
        assert is_alarm_entity(ent) is True

    def test_rejects_non_binary_sensor_platform(self) -> None:
        """Non binary_sensor platforms are never alarm entities, even with an
        alarm-like name.
        """
        ent = EntityDef(platform="sensor", name="Alarm Test", address=102)
        assert is_alarm_entity(ent) is False
