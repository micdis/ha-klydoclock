"""Find the clock's current ADB address and port via mDNS.

From Clock OS 642 on, adbd no longer listens on the fixed port 5555. It picks
a port at every start and announces it via mDNS (DNS-SD) under the instance
name ``adb-<serial>``. This module looks up that announcement: by the clock's
serial number when it is known, otherwise by its IP address.
"""

from __future__ import annotations

import asyncio
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


async def async_find_endpoint(
    hass: HomeAssistant, host: str, serial: str | None = None
) -> tuple[str, int] | None:
    """Return (address, port) the clock announces for ADB, or None.

    With a serial, the announcement is matched by name and may carry a new
    address. Without one, or if no name matches, it is matched by host.
    """
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

    # Announcements named after the serial first, then all others by address.
    candidates = sorted(
        names,
        key=lambda item: not (serial and name_matches_serial(item[1], item[0], serial)),
    )
    for service_type, name in candidates:
        by_serial = bool(serial and name_matches_serial(name, service_type, serial))
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(aiozc.zeroconf, RESOLVE_TIMEOUT_MS):
            continue
        addresses = info.parsed_addresses()
        if not info.port or not addresses:
            continue
        if by_serial:
            address = host if host in addresses else addresses[0]
        elif host in addresses:
            address = host
        else:
            continue
        _LOGGER.debug("ADB announced at %s:%s (%s)", address, info.port, name)
        return address, info.port

    _LOGGER.debug(
        "No ADB announcement for %s (serial %s) among %d services: %s",
        host,
        serial,
        len(names),
        sorted(n for _, n in names),
    )
    return None
