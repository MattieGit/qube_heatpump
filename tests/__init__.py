"""Tests for the Qube Heat Pump integration."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from python_qube_heatpump import QubeDeviceInfo

from custom_components.qube_heatpump.const import DEFAULT_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

MDNS_INFO = QubeDeviceInfo(
    uuid="000100000007B5EA",
    software_version="4.1.00",
    controller_firmware="v5.1.007",
    project_name="DEQSIHPB000CR",
)

# The advertisement captured from a Qube on firmware 4.1.00
ZEROCONF_DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.5.208"),
    ip_addresses=[ip_address("192.168.5.208")],
    hostname="Qube.local.",
    name="Qube._workstation._tcp.local.",
    port=9,
    type="_workstation._tcp.local.",
    properties={
        "Vendor": "000A5C",
        "MachineType": "312",
        "HWCode": "344",
        "InterfaceType": "11",
        "Uuid": "000100000007B5EA",
        "FWRelease": "v5.1.007",
        "ToolRelease": "5.1.9",
        "ProjectRelease": "4.1.00",
        "ProjectName": "DEQSIHPB000CR",
    },
)


async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Add the config entry to hass and set it up."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def async_poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Advance time past one coordinator interval and let it poll the device."""
    freezer.tick(timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@contextmanager
def patch_validation_client(
    *,
    connect: bool = True,
    verified: bool = True,
    connect_side_effect: type[Exception] | Exception | None = None,
) -> Iterator[MagicMock]:
    """Patch the Modbus client the config and options flows validate a host with."""
    with patch(
        "custom_components.qube_heatpump.config_flow.QubeClient", autospec=True
    ) as client_cls:
        client = client_cls.return_value
        client.connect = AsyncMock(
            return_value=connect, side_effect=connect_side_effect
        )
        client.async_verify_device = AsyncMock(return_value=verified)
        client.close = AsyncMock()
        yield client
