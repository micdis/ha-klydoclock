"""Find the clock's current ADB address and port via mDNS.

From Clock OS 642 on, adbd no longer listens on the fixed port 5555. It picks
a port at every start and announces it via mDNS (DNS-SD) under the instance
name ``adb-<serial>``. This module looks up that announcement: by the clock's
serial number when it is known, otherwise by its IP address.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant

from .const import MDNS_BROWSE_SECONDS, MDNS_SERVICE_TYPES

_LOGGER = logging.getLogger(__name__)

RESOLVE_TIMEOUT_MS = 3000


def name_matches_serial(name: str, service_type: str, serial: str) -> bool:
    """Tell whether an mDNS service name is the announcement of this serial.

    _adb._tcp uses ``adb-<serial>``, _adb-tls-connect._tcp ``adb-<serial>-<id>``.
    """
    suffix = f".{service_type}"
    instance = name[: -len(suffix)] if name.endswith(suffix) else name
    if not instance.startswith("adb-"):
        return False
    rest = instance[len("adb-") :]
    return rest == serial or rest.startswith(f"{serial}-")


@dataclass(frozen=True)
class AdbAnnouncement:
    """One ADB service announced on the network."""

    service_type: str
    name: str
    serial: str | None
    host: str
    port: int

    @property
    def instance(self) -> str:
        """The instance name, e.g. adb-a2311igtx1f36o3y."""
        suffix = f".{self.service_type}"
        return self.name[: -len(suffix)] if self.name.endswith(suffix) else self.name


def serial_from_name(name: str, service_type: str) -> str | None:
    """Return the serial in an ``adb-<serial>`` name (TLS names keep their id)."""
    suffix = f".{service_type}"
    instance = name[: -len(suffix)] if name.endswith(suffix) else name
    return instance[len("adb-") :] if instance.startswith("adb-") else None


async def async_browse(hass: HomeAssistant) -> list[AdbAnnouncement]:
    """Return every ADB service announced on the network, resolved."""
    aiozc = await zeroconf.async_get_async_instance(hass)
    names: set[tuple[str, str]] = set()

    def on_change(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is not ServiceStateChange.Removed:
            names.add((service_type, name))

    browser = AsyncServiceBrowser(
        aiozc.zeroconf, MDNS_SERVICE_TYPES, handlers=[on_change]
    )
    try:
        await asyncio.sleep(MDNS_BROWSE_SECONDS)
    finally:
        await browser.async_cancel()

    async def resolve(service_type: str, name: str) -> list[AdbAnnouncement]:
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(aiozc.zeroconf, RESOLVE_TIMEOUT_MS):
            return []
        if not info.port:
            return []
        serial = serial_from_name(name, service_type)
        # IPv4 first: adb-shell and the stored host are IPv4 addresses.
        addresses = sorted(info.parsed_addresses(), key=lambda a: ":" in a)
        return [
            AdbAnnouncement(service_type, name, serial, address, info.port)
            for address in addresses
        ]

    results = await asyncio.gather(*(resolve(t, n) for t, n in sorted(names)))
    return [announcement for found in results for announcement in found]


async def async_find_endpoint(
    hass: HomeAssistant, host: str, serial: str | None = None
) -> tuple[str, int] | None:
    """Return (address, port) the clock announces for ADB, or None.

    With a serial, the announcement is matched by name and may carry a new
    address. Without one, or if no name matches, it is matched by host.
    """
    announcements = await async_browse(hass)
    if serial:
        mine = [
            a
            for a in announcements
            if name_matches_serial(a.name, a.service_type, serial)
        ]
        # Keep the known address if the clock still announces it.
        for a in sorted(mine, key=lambda a: a.host != host):
            _LOGGER.debug("ADB announced at %s:%s (%s)", a.host, a.port, a.name)
            return a.host, a.port
    for a in announcements:
        if a.host == host:
            _LOGGER.debug("ADB announced at %s:%s (%s)", a.host, a.port, a.name)
            return a.host, a.port

    _LOGGER.debug(
        "No ADB announcement for %s (serial %s) among: %s",
        host,
        serial,
        sorted({a.name for a in announcements}),
    )
    return None
