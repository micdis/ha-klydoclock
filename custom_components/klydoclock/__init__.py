"""The Klydoclock integration (local control over ADB)."""

from __future__ import annotations

import re

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import STORAGE_DIR

from .adb import KlydoAdb, KlydoConnectionError, KlydoRootError, load_signer
from .const import ADB_KEY_FILE, DEFAULT_PORT, PACKAGE
from .coordinator import KlydoConfigEntry, KlydoCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_get_adb(hass: HomeAssistant, host: str, port: int) -> KlydoAdb:
    """Create an ADB client using the integration's key pair."""
    signer = await hass.async_add_executor_job(
        load_signer, hass.config.path(STORAGE_DIR, ADB_KEY_FILE)
    )
    return KlydoAdb(host, port, signer)


async def async_setup_entry(hass: HomeAssistant, entry: KlydoConfigEntry) -> bool:
    """Set up a clock from a config entry."""
    adb = await async_get_adb(
        hass, entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )
    coordinator = KlydoCoordinator(hass, entry, adb)
    try:
        version = await adb.shell(f"dumpsys package {PACKAGE} | grep versionName")
    except (KlydoConnectionError, KlydoRootError) as err:
        await adb.close()
        raise ConfigEntryNotReady(str(err)) from err
    if match := re.search(r"versionName=(\S+)", version):
        coordinator.app_version = match.group(1)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await adb.close()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KlydoConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.adb.close()
    return unloaded
