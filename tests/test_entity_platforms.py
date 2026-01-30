"""Tests for entity platform edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.qube_heatpump.const import CONF_HOST, DOMAIN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


class TestSwitchUniqueIdFallback:
    """Tests for switch unique_id fallback logic."""

    async def test_switch_unique_id_fallback(self, hass: HomeAssistant) -> None:
        """Test switch uses write_type in unique_id when unique_id not set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="Test Switch",
            address=100,
            write_type="coil",
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.vendor_id = None

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert switch._attr_unique_id == "qube_switch_coil_100"

    async def test_switch_unique_id_multi_device(self, hass: HomeAssistant) -> None:
        """Test switch unique_id includes label in multi_device mode."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="Test Switch",
            address=100,
        )
        ent.unique_id = None
        ent.translation_key = None
        ent.vendor_id = None
        ent.write_type = None

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            show_label=True,
            multi_device=True,
            ent=ent,
        )

        assert "qube1" in switch._attr_unique_id

    async def test_switch_translation_key_fallback(self, hass: HomeAssistant) -> None:
        """Test switch uses translation_key when set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="Test Switch",
            address=100,
            translation_key="my_switch",
        )
        ent.unique_id = "test_unique"
        ent.vendor_id = None

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert switch._attr_translation_key == "my_switch"
        assert switch._attr_has_entity_name is True

    async def test_switch_name_fallback(self, hass: HomeAssistant) -> None:
        """Test switch uses name when translation_key not set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="My Test Switch",
            address=100,
        )
        ent.unique_id = "test_unique"
        ent.translation_key = None
        ent.vendor_id = None

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert switch._attr_name == "My Test Switch"


class TestBinarySensorUniqueIdFallback:
    """Tests for binary_sensor unique_id fallback logic."""

    async def test_binary_sensor_unique_id_fallback(
        self, hass: HomeAssistant
    ) -> None:
        """Test binary sensor uses input_type in unique_id when unique_id not set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

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
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert sensor._attr_unique_id == "qube_binary_discrete_5"

    async def test_binary_sensor_unique_id_multi_device(
        self, hass: HomeAssistant
    ) -> None:
        """Test binary sensor unique_id includes label in multi_device mode."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

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
            show_label=True,
            multi_device=True,
            ent=ent,
        )

        assert "qube1" in sensor._attr_unique_id

    async def test_binary_sensor_translation_key_fallback(
        self, hass: HomeAssistant
    ) -> None:
        """Test binary sensor uses translation_key when set."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

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
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert sensor._attr_translation_key == "my_sensor"
        assert sensor._attr_has_entity_name is True


class TestBinarySensorAlarmHelpers:
    """Tests for binary sensor alarm helper functions."""

    def test_is_alarm_entity_wrong_platform(self) -> None:
        """Test _is_alarm_entity returns False for non-binary_sensor."""
        from custom_components.qube_heatpump.binary_sensor import _is_alarm_entity
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(platform="sensor", name="Alarm Test", address=100)
        assert _is_alarm_entity(ent) is False

    def test_is_alarm_entity_by_name(self) -> None:
        """Test _is_alarm_entity detects alarm in name."""
        from custom_components.qube_heatpump.binary_sensor import _is_alarm_entity
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(platform="binary_sensor", name="Some Alarm Sensor", address=100)
        assert _is_alarm_entity(ent) is True

    def test_is_alarm_entity_by_vendor_id(self) -> None:
        """Test _is_alarm_entity detects vendor_id starting with 'al'."""
        from custom_components.qube_heatpump.binary_sensor import _is_alarm_entity
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(
            platform="binary_sensor", name="Test", address=100, vendor_id="alarm_xyz"
        )
        assert _is_alarm_entity(ent) is True

    def test_is_alarm_entity_not_alarm(self) -> None:
        """Test _is_alarm_entity returns False for non-alarm."""
        from custom_components.qube_heatpump.binary_sensor import _is_alarm_entity
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(
            platform="binary_sensor", name="Temperature", address=100, vendor_id="temp"
        )
        assert _is_alarm_entity(ent) is False

    def test_entity_state_key_with_unique_id(self) -> None:
        """Test _entity_state_key returns unique_id when set."""
        from custom_components.qube_heatpump.binary_sensor import _entity_state_key
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(
            platform="binary_sensor",
            name="Test",
            address=100,
            unique_id="my_unique_id",
        )
        assert _entity_state_key(ent) == "my_unique_id"

    def test_entity_state_key_fallback(self) -> None:
        """Test _entity_state_key returns generated key when no unique_id."""
        from custom_components.qube_heatpump.binary_sensor import _entity_state_key
        from custom_components.qube_heatpump.hub import EntityDef

        ent = EntityDef(
            platform="binary_sensor",
            name="Test",
            address=100,
            input_type="discrete",
        )
        ent.unique_id = None
        assert _entity_state_key(ent) == "binary_sensor_discrete_100"


class TestEnsureEntityIdHelper:
    """Tests for _async_ensure_entity_id helper functions."""

    def test_switch_slugify(self) -> None:
        """Test switch slugify function."""
        from custom_components.qube_heatpump.switch import _slugify

        assert _slugify("Hello World") == "hello_world"
        assert _slugify("test-123") == "test_123"
        assert _slugify("CamelCase") == "camelcase"

    def test_binary_sensor_slugify(self) -> None:
        """Test binary_sensor slugify function."""
        from custom_components.qube_heatpump.binary_sensor import _slugify

        assert _slugify("Hello World") == "hello_world"
        assert _slugify("test-123") == "test_123"
        assert _slugify("CamelCase") == "camelcase"


class TestSwitchSGReady:
    """Tests for switch SG Ready handling."""

    async def test_switch_sgready_properties(self, hass: HomeAssistant) -> None:
        """Test SG Ready switch has correct properties."""
        from custom_components.qube_heatpump.hub import EntityDef
        from custom_components.qube_heatpump.switch import QubeSwitch
        from homeassistant.const import EntityCategory

        hub = MagicMock()
        hub.host = "1.2.3.4"
        hub.unit = 1
        hub.label = "qube1"
        hub.get_friendly_name = MagicMock(return_value=None)

        coordinator = MagicMock()
        coordinator.data = {}

        ent = EntityDef(
            platform="switch",
            name="SG Ready A",
            address=100,
            vendor_id="bms_sgready_a",
        )
        ent.unique_id = "sgready_a"
        ent.translation_key = None

        switch = QubeSwitch(
            coordinator=coordinator,
            hub=hub,
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        # SG Ready switches should be hidden and in config category
        assert switch._attr_entity_registry_visible_default is False
        assert switch._attr_entity_category == EntityCategory.CONFIG


async def test_switch_vendor_id_suggested_object_id(
    hass: HomeAssistant,
) -> None:
    """Test switch suggested_object_id from vendor_id."""
    from custom_components.qube_heatpump.hub import EntityDef
    from custom_components.qube_heatpump.switch import QubeSwitch

    hub = MagicMock()
    hub.host = "1.2.3.4"
    hub.unit = 1
    hub.label = "qube1"
    hub.get_friendly_name = MagicMock(return_value=None)

    coordinator = MagicMock()
    coordinator.data = {}

    ent = EntityDef(
        platform="switch",
        name="Test Switch",
        address=100,
        vendor_id="my_vendor_switch",
    )
    ent.unique_id = "test_unique"
    ent.translation_key = None

    # Without show_label
    switch = QubeSwitch(
        coordinator=coordinator,
        hub=hub,
        show_label=False,
        multi_device=False,
        ent=ent,
    )
    assert switch._attr_suggested_object_id == "my_vendor_switch"

    # With show_label
    switch2 = QubeSwitch(
        coordinator=coordinator,
        hub=hub,
        show_label=True,
        multi_device=True,
        ent=ent,
    )
    assert "qube1" in switch2._attr_suggested_object_id


async def test_binary_sensor_hidden_vendor_ids(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor with hidden vendor IDs."""
    from custom_components.qube_heatpump.hub import EntityDef
    from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor

    hub = MagicMock()
    hub.host = "1.2.3.4"
    hub.unit = 1
    hub.label = "qube1"
    hub.get_friendly_name = MagicMock(return_value=None)

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
            show_label=False,
            multi_device=False,
            ent=ent,
        )

        assert sensor._attr_entity_registry_visible_default is False
        assert sensor._attr_entity_registry_enabled_default is False
