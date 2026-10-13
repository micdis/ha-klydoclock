"""The Klydoclock integration (local control over ADB)."""

from __future__ import annotations

from pathlib import Path
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType

from .adb import KlydoAdb, KlydoConnectionError, KlydoRootError, load_signer
from .const import (
    ADB_KEY_FILE,
    ATTR_KLYDO,
    ATTR_MODE,
    ATTR_VIDEO,
    DEFAULT_PORT,
    DOMAIN,
    MAX_VIDEO_BYTES,
    MODES,
    PACKAGE,
    SERVICE_SET_MODE,
    SERVICE_SHOW_KLYDO,
    SERVICE_SHOW_VIDEO,
)
from .coordinator import KlydoConfigEntry, KlydoCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SHOW_KLYDO_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KLYDO): cv.string,
        vol.Optional(ATTR_MODE): vol.In(list(MODES)),
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)

SET_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MODE): vol.In(list(MODES)),
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)

SHOW_VIDEO_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_VIDEO): cv.string,
        vol.Required(ATTR_KLYDO): cv.string,
        vol.Optional(ATTR_MODE): vol.In(list(MODES)),
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)


def _coordinator_for(hass: HomeAssistant, call: ServiceCall) -> KlydoCoordinator:
    """Return the coordinator of the clock a service call is aimed at."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if device_id := call.data.get(ATTR_DEVICE_ID):
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device: {device_id}")
        entries = [e for e in entries if e.entry_id in device.config_entries]
    if not entries:
        raise ServiceValidationError("No Klydoclock is set up and loaded")
    if len(entries) > 1:
        raise ServiceValidationError("More than one Klydoclock is set up; pass device_id")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""

    async def show_klydo(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call)
        klydo_id = coordinator.resolve_klydo_id(call.data[ATTR_KLYDO])
        mode = call.data.get(ATTR_MODE)
        await coordinator.async_show_klydo(klydo_id, MODES[mode] if mode else None)

    async def set_mode(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call)
        await coordinator.async_set_mode(MODES[call.data[ATTR_MODE]])

    async def show_video(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call)
        video = await hass.async_add_executor_job(
            _video_file, hass.config.config_dir, call.data[ATTR_VIDEO]
        )
        klydo_id = coordinator.resolve_klydo_id(call.data[ATTR_KLYDO])
        mode = call.data.get(ATTR_MODE)
        await coordinator.async_show_video(
            video, klydo_id, MODES[mode] if mode else None
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SHOW_KLYDO, show_klydo, schema=SHOW_KLYDO_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_MODE, set_mode, schema=SET_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SHOW_VIDEO, show_video, schema=SHOW_VIDEO_SCHEMA
    )
    return True


def _video_file(config_dir: str, value: str) -> Path:
    """Resolve a video path inside the config directory and check it. Blocking."""
    base = Path(config_dir).resolve()
    path = (base / value).resolve()  # an absolute value replaces base
    if base not in path.parents:
        raise ServiceValidationError(
            f"The video must be inside the Home Assistant config directory: {value}"
        )
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise ServiceValidationError(f"No MP4 file at {path}")
    if path.stat().st_size > MAX_VIDEO_BYTES:
        raise ServiceValidationError(
            f"The video is larger than {MAX_VIDEO_BYTES // (1024 * 1024)} MB"
        )
    return path


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
    entry.runtime_data.cancel_navigation()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.adb.close()
    return unloaded
