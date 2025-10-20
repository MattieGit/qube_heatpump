from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import device_registry as dr

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_UNIT_ID,
    CONF_SHOW_LABEL_IN_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def bypass_modbus_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip loading the Modbus dependency during config flow tests."""

    async def fake_async_process_deps_reqs(hass, config, integration):  # type: ignore[unused-arg]
        return None

    monkeypatch.setattr(
        "homeassistant.setup.async_process_deps_reqs",
        fake_async_process_deps_reqs,
    )
    monkeypatch.setattr(
        "homeassistant.config_entries.async_process_deps_reqs",
        fake_async_process_deps_reqs,
    )


class _DummyWriter:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_config_flow_blocks_duplicate_ip(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the user flow rejects hosts that resolve to an existing hub IP."""

    existing = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT})
    existing.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        mapping = {"qube.local": "192.0.2.55", "192.0.2.55": "192.0.2.55"}
        return mapping.get(host)

    async def fake_open_connection(host: str, port: int) -> tuple[Any, _DummyWriter]:
        return object(), _DummyWriter()

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )
    monkeypatch.setattr("asyncio.open_connection", fake_open_connection)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.0.2.55"},
    )
    assert result2["type"] == "form"
    assert result2["errors"][CONF_HOST] == "duplicate_ip"


@pytest.mark.asyncio
async def test_reconfigure_rejects_duplicate_ip(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure reconfigure flow aborts when the new host resolves to an existing hub IP."""

    existing = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT})
    existing.add_to_hass(hass)

    target = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "qube2.local", CONF_PORT: DEFAULT_PORT})
    target.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        mapping = {
            "qube.local": "192.0.2.55",
            "qube2.local": "192.0.2.56",
            "192.0.2.55": "192.0.2.55",
        }
        return mapping.get(host)

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )

    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": target.entry_id},
        data={"entry_id": target.entry_id},
    )
    assert flow["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "duplicate_ip"


@pytest.mark.asyncio
async def test_options_form_includes_resolved_ip(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """The options form exposes the resolved IP address in the description placeholders."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT},
        options={CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        return {"qube.local": "192.0.2.55"}.get(host)

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["description_placeholders"]["resolved_ip"] == "192.0.2.55"


@pytest.mark.asyncio
async def test_options_updates_host_when_connection_succeeds(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Updating the host via options requires a successful connection and reloads the entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT},
        options={CONF_UNIT_ID: 1},
        unique_id=f"{DOMAIN}-qube.local-{DEFAULT_PORT}",
    )
    entry.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        mapping = {
            "qube.local": "192.0.2.55",
            "192.0.2.99": "192.0.2.99",
            "qube.new": "192.0.2.99",
        }
        return mapping.get(host)

    async def fake_open_connection(host: str, port: int) -> tuple[Any, _DummyWriter]:
        return object(), _DummyWriter()

    reload_mock = AsyncMock()

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "qube.local:1")},
    )

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )
    monkeypatch.setattr("asyncio.open_connection", fake_open_connection)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {CONF_HOST: "qube.new", CONF_SHOW_LABEL_IN_NAME: False},
    )
    assert result["type"] == "create_entry"
    assert entry.data[CONF_HOST] == "qube.new"
    assert entry.unique_id == f"{DOMAIN}-qube.new-{DEFAULT_PORT}"
    reload_mock.assert_awaited_once_with(entry.entry_id)
    assert (
        device_registry.async_get_device({(DOMAIN, "qube.local:1")}) is None
    )
    assert CONF_UNIT_ID not in entry.options


@pytest.mark.asyncio
async def test_options_rejects_duplicate_host(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Options flow rejects hosts that resolve to an existing entry."""

    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT},
        options={CONF_UNIT_ID: 1},
    )
    existing.add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "qube2.local", CONF_PORT: DEFAULT_PORT},
        options={CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        mapping = {
            "qube.local": "192.0.2.55",
            "qube2.local": "192.0.2.56",
            "duplicate.local": "192.0.2.55",
        }
        return mapping.get(host)

    async def fake_open_connection(host: str, port: int) -> tuple[Any, _DummyWriter]:
        return object(), _DummyWriter()

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )
    monkeypatch.setattr("asyncio.open_connection", fake_open_connection)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {CONF_HOST: "duplicate.local", CONF_SHOW_LABEL_IN_NAME: False},
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_HOST] == "duplicate_ip"


@pytest.mark.asyncio
async def test_options_rejects_connection_failure(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Options flow keeps the existing host when the connectivity test fails."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "qube.local", CONF_PORT: DEFAULT_PORT},
        options={CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)

    async def fake_resolve(host: str) -> str | None:
        mapping = {
            "qube.local": "192.0.2.55",
            "bad.host": "192.0.2.77",
        }
        return mapping.get(host)

    async def failing_open_connection(host: str, port: int) -> tuple[Any, _DummyWriter]:
        raise OSError("cannot connect")

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow._async_resolve_host",
        fake_resolve,
    )
    monkeypatch.setattr("asyncio.open_connection", failing_open_connection)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {CONF_HOST: "bad.host", CONF_SHOW_LABEL_IN_NAME: False},
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_HOST] == "cannot_connect"
    assert entry.data[CONF_HOST] == "qube.local"
