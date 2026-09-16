"""Unit tests for entity identity: unique_id, entity_id and coordinator keys.

Platform behaviour is covered by the per-platform modules against a real
set up entry. What is left here are the fallbacks that no library entity
reaches, so they can only be exercised by constructing an EntityDef.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.qube_heatpump.binary_sensor import QubeBinarySensor
from custom_components.qube_heatpump.entity_defs import EntityDef
from custom_components.qube_heatpump.helpers import entity_data_key
from custom_components.qube_heatpump.switch import QubeSwitch


@pytest.fixture
def hub() -> MagicMock:
    """Return a hub stub with the attributes entity identity is built from."""
    return MagicMock(host="1.2.3.4", unit=1, label="qube1")


@pytest.fixture
def coordinator() -> MagicMock:
    """Return a coordinator stub holding no values, owned by entry "entry-1"."""
    coordinator = MagicMock(data={})
    coordinator.config_entry.entry_id = "entry-1"
    return coordinator


def test_switch_identity_comes_from_the_library_key(
    hub: MagicMock, coordinator: MagicMock
) -> None:
    """unique_id, entity_id and translation key are all derived from the key."""
    ent = EntityDef(
        platform="switch",
        name="Test Switch",
        address=100,
        vendor_id="my_switch",
        unique_id="my_switch",
        translation_key="my_switch",
        write_type="coil",
    )

    switch = QubeSwitch(coordinator=coordinator, hub=hub, ent=ent)

    assert switch.unique_id == "entry-1_my_switch"
    assert switch.entity_id == "switch.qube1_my_switch"
    assert switch.translation_key == "my_switch"
    assert switch.has_entity_name is True


@pytest.mark.parametrize(
    ("input_type", "expected_unique_id"),
    [
        ("discrete", "entry-1_qube_binary_discrete_5"),
        (None, "entry-1_qube_binary_input_5"),
    ],
)
def test_binary_sensor_unique_id_falls_back_to_address(
    hub: MagicMock,
    coordinator: MagicMock,
    input_type: str | None,
    expected_unique_id: str,
) -> None:
    """Without a library key the unique_id is built from input type and address.

    It stays scoped by host and unit so two devices never collide.
    """
    ent = EntityDef(
        platform="binary_sensor",
        name="Test Binary",
        address=5,
        input_type=input_type,
    )
    ent.unique_id = None
    ent.translation_key = None
    ent.vendor_id = None

    sensor = QubeBinarySensor(coordinator=coordinator, hub=hub, ent=ent)

    assert sensor.unique_id == expected_unique_id
    # No vendor_id means no entity_id override; HA derives it from the name
    assert sensor.name == "Test Binary"


def test_binary_sensor_prefers_translation_key_over_name(
    hub: MagicMock, coordinator: MagicMock
) -> None:
    """A translated entity is named through the key, not the library string."""
    ent = EntityDef(
        platform="binary_sensor",
        name="Test Binary",
        address=5,
        unique_id="test_unique",
        translation_key="my_sensor",
    )
    ent.vendor_id = None

    sensor = QubeBinarySensor(coordinator=coordinator, hub=hub, ent=ent)

    assert sensor.translation_key == "my_sensor"
    assert sensor.has_entity_name is True
    # The raw library name must not shadow the translation
    assert getattr(sensor, "_attr_name", None) is None


@pytest.mark.parametrize(
    ("unique_id", "expected_key"),
    [
        ("my_unique_id", "my_unique_id"),
        (None, "binary_sensor_discrete_100"),
    ],
)
def test_entity_data_key(unique_id: str | None, expected_key: str) -> None:
    """The coordinator key is the library key, or a stable synthetic one."""
    ent = EntityDef(
        platform="binary_sensor",
        name="Test",
        address=100,
        input_type="discrete",
    )
    ent.unique_id = unique_id

    assert entity_data_key(ent) == expected_key
