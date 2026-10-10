"""Data update coordinator for the Klydoclock."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .adb import KlydoAdb, KlydoConnectionError, KlydoRootError
from .catalog import Klydo, load_catalog
from .const import (
    ARTISTS_PATH,
    BRIGHTNESS_TO_MODE,
    CATALOG_MIN_REFRESH,
    DATABASE_PATH,
    DISPLAY_MODES,
    DISPLAY_NIGHT,
    DISPLAY_OFF,
    DOMAIN,
    KEY_SLEEP,
    SCAN_INTERVAL,
    SETTINGS_PATH,
)
from .datastore import parse_preferences

_LOGGER = logging.getLogger(__name__)

type KlydoConfigEntry = ConfigEntry[KlydoCoordinator]


@dataclass(slots=True)
class KlydoState:
    """Snapshot of the clock."""

    settings: dict[str, Any]
    klydo_id: str | None
    klydo: Klydo | None
    favorites: list[str] = field(default_factory=list)
    feed: list[str] = field(default_factory=list)
    artist: str | None = None

    @property
    def display_mode(self) -> str | None:
        """Return the stage of the sleep-key cycle the display is in."""
        screen = self.setting("screenState")
        if screen == "OFF":
            return DISPLAY_OFF
        if screen == "NIGHTMODE":
            return DISPLAY_NIGHT
        if screen == "DEFAULT":
            return BRIGHTNESS_TO_MODE.get(str(self.setting("brightness")))
        return None

    @property
    def display_stamp(self) -> tuple[Any, Any]:
        """Change markers of the settings the sleep key touches."""
        return (
            self.settings.get("brightness_time"),
            self.settings.get("screenState_time"),
        )

    def setting(self, name: str) -> Any:
        """Return the value of a synced setting."""
        return self.settings.get(f"{name}_value")

    def changed(self, name: str) -> datetime | None:
        """Return when a synced setting was last changed on the clock."""
        millis = self.settings.get(f"{name}_time")
        if not isinstance(millis, int) or millis <= 0:
            return None
        return dt_util.utc_from_timestamp(millis / 1000)

    @property
    def is_favorite(self) -> bool | None:
        """Return whether the current klydo is a favorite."""
        return None if self.klydo_id is None else self.klydo_id in self.favorites


def _json_list(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


class KlydoCoordinator(DataUpdateCoordinator[KlydoState]):
    """Poll the clock's settings store over ADB."""

    config_entry: KlydoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: KlydoConfigEntry, adb: KlydoAdb
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {adb.host}",
            update_interval=SCAN_INTERVAL,
        )
        self.adb = adb
        self.catalog: dict[str, Klydo] = {}
        self.artists: dict[str, str] = {}
        self._display_lock = asyncio.Lock()
        self.app_version: str | None = None
        self._catalog_loaded: datetime | None = None

    async def _load_catalog(self) -> None:
        database = await self.adb.read_file(DATABASE_PATH)
        if not database:
            raise UpdateFailed("klydo database is empty or unreadable")
        wal = await self.adb.read_file(f"{DATABASE_PATH}-wal")
        try:
            self.catalog = await self.hass.async_add_executor_job(
                load_catalog, database, wal
            )
        except Exception:  # noqa: BLE001 - db and wal may be read mid-write
            self.catalog = await self.hass.async_add_executor_job(
                load_catalog, database, None
            )
        self._catalog_loaded = dt_util.utcnow()
        try:
            artists = parse_preferences(await self.adb.read_file(ARTISTS_PATH))
            self.artists = {
                key: name
                for key, raw in artists.items()
                if isinstance(raw, str)
                and isinstance(name := json.loads(raw).get("name"), str)
            }
        except (ValueError, IndexError, AttributeError) as err:
            _LOGGER.debug("Artist cache not readable: %s", err)
        _LOGGER.debug("Loaded %s klydos from the clock", len(self.catalog))

    async def _async_update_data(self) -> KlydoState:
        try:
            raw = await self.adb.read_file(SETTINGS_PATH)
            if not raw:
                raise UpdateFailed("settings store is empty or unreadable")
            try:
                settings = parse_preferences(raw)
            except (ValueError, IndexError) as err:
                # The app rewrites the file atomically, but be tolerant anyway.
                raise UpdateFailed(f"settings store not parseable: {err}") from err

            klydo_id = settings.get("klydo_value")
            klydo_id = klydo_id if isinstance(klydo_id, str) and klydo_id else None

            stale = (
                self._catalog_loaded is None
                or dt_util.utcnow() - self._catalog_loaded > CATALOG_MIN_REFRESH
            )
            if not self.catalog or (klydo_id and klydo_id not in self.catalog and stale):
                await self._load_catalog()
        except KlydoRootError as err:
            raise UpdateFailed(f"root access refused: {err}") from err
        except KlydoConnectionError as err:
            raise UpdateFailed(str(err)) from err

        klydo = self.catalog.get(klydo_id) if klydo_id else None
        return KlydoState(
            settings=settings,
            klydo_id=klydo_id,
            klydo=klydo,
            artist=self.artists.get(klydo.creator) if klydo and klydo.creator else None,
            favorites=_json_list(settings.get("favorites_value")),
            feed=_json_list(settings.get("feeds_value")),
        )

    async def async_press_key(self, keycode: int) -> None:
        """Send a remote key and pick up the result shortly after."""
        await self.adb.keyevent(keycode)

        async def _refresh_later() -> None:
            # Klydo changes land in the store within ~0.3 s, favorites take ~3 s.
            for delay in (1.0, 3.0):
                await asyncio.sleep(delay)
                await self.async_refresh()

        self.config_entry.async_create_background_task(
            self.hass, _refresh_later(), f"{DOMAIN}_refresh_after_key"
        )

    async def async_set_display_mode(self, target: str) -> None:
        """Press the sleep key until the display is in the wanted mode."""
        if target not in DISPLAY_MODES:
            raise HomeAssistantError(f"Unknown display mode: {target}")
        async with self._display_lock:
            try:
                state = await self._async_update_data()
                # One full cycle is five presses; allow one spare.
                for _ in range(len(DISPLAY_MODES) + 1):
                    if state.display_mode == target:
                        break
                    stamp = state.display_stamp
                    await self.adb.keyevent(KEY_SLEEP)
                    for _ in range(12):  # the app persists a change within ~0.3 s
                        await asyncio.sleep(0.35)
                        state = await self._async_update_data()
                        if state.display_stamp != stamp:
                            break
                    else:
                        raise HomeAssistantError(
                            "Klydoclock did not react to the sleep key"
                        )
                else:
                    raise HomeAssistantError(
                        f"Klydoclock did not reach display mode {target}"
                    )
            except UpdateFailed as err:
                raise HomeAssistantError(f"Klydoclock: {err}") from err
            finally:
                await self.async_refresh()
