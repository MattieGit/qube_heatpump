"""Tests for entity platform edge cases."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class TestSwitchIdentity:
    """Tests for switch unique_id / naming derived from the library key."""

    async def test_switch_unique_id_and_translation_key(
        self, hass: HomeAssistant
    ) -> None:
        """The scoped unique_id and translation key both come from the library key."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="Test Switch",
            address=100,
            vendor_id="my_switch",
            unique_id="my_switch",
            translation_key="my_switch",
            write_type="coil",
        )

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            ent=ent,
        )

        assert switch._attr_unique_id == "1.2.3.4_1_my_switch"
        assert switch.entity_id == "switch.qube1_my_switch"
        assert switch._attr_translation_key == "my_switch"
        assert switch._attr_has_entity_name is True


class TestBinarySensorUniqueIdFallback:
    """Tests for binary_sensor unique_id fallback logic."""

    async def test_binary_sensor_unique_id_fallback(self, hass: HomeAssistant) -> None:
        """Test binary sensor uses input_type in unique_id when unique_id not set."""
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor
        from custom_components.qube_heatpump.entity_defs import EntityDef

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="binary_sensor",
            name="Test Binary",
            address=5,
            input_type="discrete",
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.vendor_id = None

        sensor = QubeBinarySensor(
            coordinator=coordinator,
            hub=hub,
            ent=ent,
        )

        # Always scoped with host_unit prefix for stability
        assert sensor._attr_unique_id == "1.2.3.4_1_qube_binary_discrete_5"

    async def test_binary_sensor_unique_id_multi_device(
        self, hass: HomeAssistant
    ) -> None:
        """Test binary sensor unique_id includes label in multi_device mode."""
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor
        from custom_components.qube_heatpump.entity_defs import EntityDef

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="binary_sensor",
            name="Test Binary",
            address=5,
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.vendor_id = None
        ent.input_type = None

        sensor = QubeBinarySensor(
            coordinator=coordinator,
            hub=hub,
            ent=ent,
        )

        # Multi-device unique_id has host_unit prefix for isolation
        assert sensor._attr_unique_id.startswith("1.2.3.4_1_")

    async def test_binary_sensor_translation_key_fallback(
        self, hass: HomeAssistant
    ) -> None:
        """Test binary sensor uses translation_key when set."""
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor
        from custom_components.qube_heatpump.entity_defs import EntityDef

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="binary_sensor",
            name="Test Binary",
            address=5,
            translation_key="my_sensor",
        )
        ent.unique_id = "test_unique"
        ent.vendor_id = None

        sensor = QubeBinarySensor(
            coordinator=coordinator,
            hub=hub,
            ent=ent,
        )

        assert sensor._attr_translation_key == "my_sensor"
        assert sensor._attr_has_entity_name is True


class TestBinarySensorAlarmHelpers:
    """Tests for binary sensor alarm helper functions."""

    def test_is_alarm_entity_wrong_platform(self) -> None:
        """Test is_alarm_entity returns False for non-binary_sensor."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import is_alarm_entity

        ent = EntityDef(platform="sensor", name="Alarm Test", address=100)
        assert is_alarm_entity(ent) is False

    def test_is_alarm_entity_by_name(self) -> None:
        """Test is_alarm_entity detects alarm in name."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import is_alarm_entity

        ent = EntityDef(platform="binary_sensor", name="Some Alarm Sensor", address=100)
        assert is_alarm_entity(ent) is True

    def test_is_alarm_entity_by_vendor_id(self) -> None:
        """Test is_alarm_entity detects vendor_id starting with 'al'."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import is_alarm_entity

        ent = EntityDef(
            platform="binary_sensor", name="Test", address=100, vendor_id="alarm_xyz"
        )
        assert is_alarm_entity(ent) is True

    def test_is_alarm_entity_not_alarm(self) -> None:
        """Test is_alarm_entity returns False for non-alarm."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import is_alarm_entity

        ent = EntityDef(
            platform="binary_sensor", name="Temperature", address=100, vendor_id="temp"
        )
        assert is_alarm_entity(ent) is False

    def test_entity_state_key_with_unique_id(self) -> None:
        """Test entity_data_key returns unique_id when set."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import entity_data_key

        ent = EntityDef(
            platform="binary_sensor",
            name="Test",
            address=100,
            unique_id="my_unique_id",
        )
        assert entity_data_key(ent) == "my_unique_id"

    def test_entity_state_key_fallback(self) -> None:
        """Test entity_data_key returns generated key when no unique_id."""
        from custom_components.qube_heatpump.entity_defs import EntityDef
        from custom_components.qube_heatpump.helpers import entity_data_key

        ent = EntityDef(
            platform="binary_sensor",
            name="Test",
            address=100,
            input_type="discrete",
        )
        ent.unique_id = None
        assert entity_data_key(ent) == "binary_sensor_discrete_100"


async def test_sgready_coils_have_no_switch_entities(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """The SG Ready coils are only exposed through the select entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        title="Qube Heat Pump",
        unique_id=f"{DOMAIN}-1.2.3.4-502",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("switch.qube_1_bms_sgready_a") is None
    assert hass.states.get("switch.qube_1_bms_sgready_b") is None
    assert hass.states.get("select.qube_1_sg_ready_mode") is not None


async def test_binary_sensor_hidden_vendor_ids(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor with hidden vendor IDs."""
    from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor
    from custom_components.qube_heatpump.entity_defs import EntityDef

    hub = MagicMock()
    hub.host = "1.2.3.4"
    hub.unit = 1
    hub.label = "qube1"

    coordinator = MagicMock()
    coordinator.data = {}

    for vendor_id in ["dout_threewayvlv_val", "dout_fourwayvlv_val"]:
        ent = EntityDef(
            platform="binary_sensor",
            name="Test",
            address=5,
            vendor_id=vendor_id,
        )
        ent.unique_id = f"test_{vendor_id}"
        ent.translation_key = None

        sensor = QubeBinarySensor(
            coordinator=coordinator,
            hub=hub,
            ent=ent,
        )

        assert sensor._attr_entity_registry_visible_default is False
        assert sensor._attr_entity_registry_enabled_default is False
