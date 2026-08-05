"""Snapshot test guarding entity_id / unique_id stability across refactors.

This test sets up the integration (twice: once with default options, once
with the virtual thermostat enabled so climate + the thermostat-timeout
binary sensor are also covered) and compares every entity registered for the
config entry against a committed snapshot. If entity_id or unique_id for any
entity ever changes, this test fails loudly.

If the snapshot file is missing entirely, it is created and the test fails
with a message asking to re-run - this is intentional so a snapshot is never
silently accepted on first creation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_THERMOSTAT_ENABLED,
    CONF_THERMOSTAT_SENSOR,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "entity_ids.json"


def _collect_entities(hass: HomeAssistant, entry: MockConfigEntry) -> list[dict]:
    """Collect every registry entry belonging to a config entry.

    Returns a deterministic, sorted list of the fields that must never
    change: entity_id, unique_id, and the entity's platform (domain).
    """
    registry = er.async_get(hass)
    rows = [
        {
            "entity_id": entity.entity_id,
            "unique_id": entity.unique_id,
            "platform": entity.domain,
        }
        for entity in registry.entities.values()
        if entity.config_entry_id == entry.entry_id
    ]
    return sorted(rows, key=lambda row: row["entity_id"])


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    return json.loads(SNAPSHOT_PATH.read_text())


def _write_snapshot(snapshot: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def _check_snapshot(scenario: str, actual: list[dict]) -> None:
    """Compare actual entities against the committed snapshot for a scenario.

    If the scenario key is missing (including a wholly missing snapshot
    file), write it and fail so the new snapshot must be reviewed and
    re-run deliberately rather than silently accepted.
    """
    snapshot = _load_snapshot()

    if scenario not in snapshot:
        snapshot[scenario] = actual
        _write_snapshot(snapshot)
        pytest.fail(
            f"Snapshot for scenario {scenario!r} was missing and has been "
            f"created at {SNAPSHOT_PATH}. Re-run the test to verify it now "
            "passes, and review the diff before committing."
        )

    assert actual == snapshot[scenario], (
        f"Entity IDs/unique IDs for scenario {scenario!r} changed! This "
        "breaks entity stability across the cleanup refactor. If the "
        f"change is intentional, delete {SNAPSHOT_PATH} and regenerate it."
    )


async def test_entity_id_snapshot_standard(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Snapshot every entity created by a standard (no-options) setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4"},
        unique_id=f"{DOMAIN}-1.2.3.4-502",
        title="Qube Heat Pump",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    actual = _collect_entities(hass, entry)
    assert actual, "No entities were created for the standard scenario"

    # Sanity check: every non-thermostat platform must be represented.
    platforms = {row["platform"] for row in actual}
    for expected in (
        "binary_sensor",
        "button",
        "number",
        "select",
        "sensor",
        "switch",
    ):
        assert expected in platforms, f"No {expected} entities were created"

    _check_snapshot("standard", actual)


async def test_entity_id_snapshot_thermostat_enabled(
    hass: HomeAssistant, mock_qube_client: MagicMock
) -> None:
    """Snapshot entities with the virtual thermostat option enabled.

    This covers the climate entity and the thermostat-timeout binary
    sensor, which only exist when CONF_THERMOSTAT_ENABLED is set.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "5.6.7.8"},
        unique_id=f"{DOMAIN}-5.6.7.8-502",
        title="Qube Heat Pump Thermostat",
        options={
            CONF_THERMOSTAT_ENABLED: True,
            CONF_THERMOSTAT_SENSOR: "sensor.outdoor_temperature",
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    actual = _collect_entities(hass, entry)
    assert actual, "No entities were created for the thermostat scenario"

    platforms = {row["platform"] for row in actual}
    assert "climate" in platforms, "Thermostat climate entity was not created"

    entity_ids = {row["entity_id"] for row in actual}
    assert any(
        "thermostat" in eid and eid.startswith("binary_sensor.")
        for eid in entity_ids
    ), "Thermostat sensor-timeout binary sensor was not created"

    _check_snapshot("thermostat_enabled", actual)
