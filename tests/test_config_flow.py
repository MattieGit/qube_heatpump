from __future__ import annotations

from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qube_heatpump.const import (
    CONF_HOST,
    CONF_PORT,
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

    async def fake_resolve(self, host: str) -> str | None:  # type: ignore[override]
        mapping = {"qube.local": "192.0.2.55", "192.0.2.55": "192.0.2.55"}
        return mapping.get(host)

    async def fake_open_connection(host: str, port: int) -> tuple[Any, _DummyWriter]:
        return object(), _DummyWriter()

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow.WPQubeConfigFlow._async_resolve_host",
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

    async def fake_resolve(self, host: str) -> str | None:  # type: ignore[override]
        mapping = {
            "qube.local": "192.0.2.55",
            "qube2.local": "192.0.2.56",
            "192.0.2.55": "192.0.2.55",
        }
        return mapping.get(host)

    monkeypatch.setattr(
        "custom_components.qube_heatpump.config_flow.WPQubeConfigFlow._async_resolve_host",
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
