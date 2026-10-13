"""Data update coordinator for the Klydoclock."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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
    KEY_ENTER,
    KEY_FAVORITE,
    KEY_INFO,
    KEY_MENU,
    KEY_NEXT,
    KEY_PREVIOUS,
    KEY_SETTINGS,
    KEY_SLEEP,
    MENU_FEED_ANGLE,
    MENU_MAX_STEPS,
    MENU_TOLERANCE,
    MODE_FAVORITE,
    MODE_FEED,
    NAV_BATCH,
    SCAN_INTERVAL,
    SETTINGS_PATH,
    UPLOAD_CHUNK,
    VIDEO_DIR,
    VIDEO_LABEL,
    VIDEO_OWNER,
)
from .datastore import parse_preferences
from .menu import angle_distance, selection_angle

_LOGGER = logging.getLogger(__name__)

type KlydoConfigEntry = ConfigEntry[KlydoCoordinator]


@dataclass(slots=True)
class KlydoState:
    """Snapshot of the clock."""

    settings: dict[str, Any]
    klydo_id: str | None
    klydo: Klydo | None
    favorites: list[str] = field(default_factory=list)
    favorite_names: list[str] = field(default_factory=list)
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
        self._nav_task: asyncio.Task | None = None
        self._night_pending = False

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
        favorites = _json_list(settings.get("favorites_value"))
        return KlydoState(
            settings=settings,
            klydo_id=klydo_id,
            klydo=klydo,
            artist=self.artists.get(klydo.creator) if klydo and klydo.creator else None,
            favorites=favorites,
            favorite_names=[
                entry.name if (entry := self.catalog.get(fav)) else fav
                for fav in favorites
            ],
            feed=_json_list(settings.get("feeds_value")),
        )

    async def async_press_key(self, keycode: int) -> None:
        """Send a remote key, leaving night mode around it when needed.

        In night mode the first key press only wakes the display, so the key
        is sent after waking and night mode restored afterwards. Info and
        settings open screens meant to be used, so those leave the display awake.
        The sleep key works in night mode and is sent as it is.
        """
        if keycode != KEY_SLEEP:
            try:
                state = await self._async_update_data()
            except UpdateFailed as err:
                raise HomeAssistantError(f"Klydoclock: {err}") from err
            if state.display_mode != DISPLAY_OFF:
                await self._run_exclusive(
                    lambda: self._press_and_settle(keycode),
                    stay_awake=keycode in (KEY_INFO, KEY_SETTINGS),
                )
                return
        await self.adb.keyevent(keycode)

        async def _refresh_later() -> None:
            # Klydo changes land in the store within ~0.3 s, favorites take ~3 s.
            for delay in (1.0, 3.0):
                await asyncio.sleep(delay)
                await self.async_refresh()

        self.config_entry.async_create_background_task(
            self.hass, _refresh_later(), f"{DOMAIN}_refresh_after_key"
        )

    def resolve_klydo_id(self, value: str) -> str:
        """Translate a klydo id or name into an id from the catalog."""
        value = value.strip()
        if value in self.catalog:
            return value
        matches = [
            k.id for k in self.catalog.values() if k.name.casefold() == value.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ServiceValidationError(f"The clock knows no klydo named '{value}'")
        raise ServiceValidationError(
            f"{len(matches)} klydos are named '{value}'; use the klydo id instead"
        )

    def cancel_navigation(self) -> None:
        """Abort a running feed navigation (newer selection, or unload)."""
        task, self._nav_task = self._nav_task, None
        if task is not None and not task.done():
            task.cancel()

    async def _read_settled_state(self) -> KlydoState:
        """Read the state once the klydo on display has stopped changing.

        Injected key events drain through the app's animation queue for a
        while after `input` returns; navigating against a still-moving
        position leads to endless corrections.
        """
        await asyncio.sleep(1.0)
        state = await self._async_update_data()
        marker = (state.klydo_id, state.settings.get("klydo_time"))
        for _ in range(12):
            await asyncio.sleep(1.2)
            state = await self._async_update_data()
            current = (state.klydo_id, state.settings.get("klydo_time"))
            if current == marker:
                return state
            marker = current
        return state

    async def async_show_klydo(self, klydo_id: str, mode: str | None = None) -> None:
        """Bring klydo_id on display, switching to FEED or FAVORITE mode if needed.

        Without a mode, the current list is used when it holds the klydo,
        otherwise the feed, otherwise the favorites.
        """
        await self._run_exclusive(lambda: self._navigate_to(klydo_id, mode))

    async def async_show_video(
        self, video: Path, klydo_id: str, mode: str | None = None
    ) -> None:
        """Make klydo_id play the given video file, then bring it on display.

        The file is only uploaded when the clock holds a different one, so a
        video the app has put back (e.g. by its nightly sync) is replaced
        again, and an unchanged one costs a single checksum.
        """
        klydo = self.catalog.get(klydo_id)
        if klydo is None:
            raise ServiceValidationError(f"The clock knows no klydo with id {klydo_id}")
        data = await self.hass.async_add_executor_job(video.read_bytes)

        async def _show() -> None:
            if await self._ensure_video(klydo.main_loop, data):
                state = await self._read_settled_state()
                if state.klydo_id == klydo_id:
                    # The player keeps the old file open; step away so that
                    # coming back opens the new one.
                    await self.adb.keyevent(KEY_NEXT)
                    await self._read_settled_state()
            await self._navigate_to(klydo_id, mode)

        await self._run_exclusive(_show)

    async def _ensure_video(self, main_loop: str, data: bytes) -> bool:
        """Put data in place as the klydo's video; return whether it was uploaded."""
        folder = f"{VIDEO_DIR}/{main_loop}"
        target = f"{folder}/{main_loop}.mp4"
        tmp = f"{folder}/.{main_loop}.mp4.tmp"
        want = hashlib.md5(data).hexdigest()
        if (await self.adb.shell(f"md5sum '{target}' 2>/dev/null")).split()[:1] == [want]:
            return False
        if await self.adb.shell(f"test -d '{folder}' && echo ok") != "ok":
            # Only the app creates klydo folders; its midnight cleanup deletes
            # any folder without a klydo in its database.
            raise HomeAssistantError(f"Klydoclock: no video folder for {main_loop}")
        await self.adb.shell(f"rm -f '{tmp}'")
        for start in range(0, len(data), UPLOAD_CHUNK):
            chunk = base64.b64encode(data[start : start + UPLOAD_CHUNK]).decode()
            if await self.adb.shell(f"echo '{chunk}' | base64 -d >> '{tmp}' && echo ok") != "ok":
                await self.adb.shell(f"rm -f '{tmp}'")
                raise HomeAssistantError("Klydoclock: video upload failed")
        if (await self.adb.shell(f"md5sum '{tmp}'")).split()[:1] != [want]:
            await self.adb.shell(f"rm -f '{tmp}'")
            raise HomeAssistantError("Klydoclock: uploaded video is corrupt")
        # Same owner, mode and SELinux label as the app's own files, then an
        # atomic rename, so the player never sees a half-written file.
        await self.adb.shell(
            f"chown {VIDEO_OWNER} '{tmp}' && chmod 664 '{tmp}' && "
            f"chcon {VIDEO_LABEL} '{tmp}' && mv -f '{tmp}' '{target}'"
        )
        if (await self.adb.shell(f"md5sum '{target}'")).split()[:1] != [want]:
            raise HomeAssistantError("Klydoclock: video could not be put in place")
        _LOGGER.info("Uploaded %s bytes as the video of %s", len(data), main_loop)
        return True

    async def async_set_mode(self, mode: str) -> None:
        """Switch the clock to FEED or FAVORITE mode through the home menu."""

        async def _set() -> None:
            state = await self._read_settled_state()
            await self._switch_mode(state, mode)

        await self._run_exclusive(_set)

    async def _press_and_settle(self, keycode: int) -> None:
        """Send a key and wait until the app has acted on it."""
        await self.adb.keyevent(keycode)
        if keycode in (KEY_NEXT, KEY_PREVIOUS):
            await self._read_settled_state()
        elif keycode == KEY_FAVORITE:
            await asyncio.sleep(3.0)  # favorites land in the store after ~3 s

    async def _run_exclusive(
        self, job: Callable[[], Awaitable[None]], stay_awake: bool = False
    ) -> None:
        """Run one navigation job or key press; a newer one cancels it."""
        self.cancel_navigation()
        self._nav_task = asyncio.current_task()
        try:
            async with self._display_lock:
                try:
                    async with self._awake(stay_awake):
                        await job()
                except UpdateFailed as err:
                    raise HomeAssistantError(f"Klydoclock: {err}") from err
                finally:
                    # Keep the entities current. Skipped when cancelled:
                    # awaiting inside a cancelled task is unsafe.
                    task = asyncio.current_task()
                    if task is None or not task.cancelling():
                        await self.async_refresh()
        except asyncio.CancelledError:
            if self._nav_task is not asyncio.current_task():
                raise HomeAssistantError(
                    "Klydo navigation was replaced by a newer selection or stopped"
                ) from None
            raise
        finally:
            if self._nav_task is asyncio.current_task():
                self._nav_task = None

    async def _menu_angle(self) -> float | None:
        png = await self.adb.screencap()
        if not png:
            return None
        return await self.hass.async_add_executor_job(selection_angle, png)

    async def _turn_menu_to(self, angle: float | None, target: float) -> float:
        """Turn the open menu until the selection arc sits at the target angle."""
        for _ in range(MENU_MAX_STEPS):
            if angle is None:
                raise HomeAssistantError("Klydoclock: home menu not recognised")
            if angle_distance(angle, target) <= MENU_TOLERANCE:
                return angle
            clockwise = (target - angle) % 360 <= 180
            await self.adb.keyevent(KEY_NEXT if clockwise else KEY_PREVIOUS)
            angle = await self._menu_angle()
        raise HomeAssistantError("Klydoclock: menu entry not reached")

    async def _switch_mode(self, state: KlydoState, mode: str) -> KlydoState:
        """Switch to FEED or FAVORITE through the home menu; runs under the lock."""
        if state.setting("mode") == mode:
            return state
        await self.adb.keyevent(KEY_MENU)
        await asyncio.sleep(1.0)
        start = await self._menu_angle()
        if start is None:
            # Nothing to confirm: either the menu did not open, or it looks
            # different from what this integration knows.
            raise HomeAssistantError("Klydoclock: home menu did not open")
        committed = False
        try:
            angle = await self._turn_menu_to(start, MENU_FEED_ANGLE)
            if mode == MODE_FAVORITE:
                await self.adb.keyevent(KEY_NEXT)
                angle = await self._menu_angle()
                if angle is None or not (
                    MENU_TOLERANCE < (angle - MENU_FEED_ANGLE) % 360 <= 120
                ):
                    raise HomeAssistantError(
                        "Klydoclock: favorites entry not found in the home menu"
                    )
            await self.adb.keyevent(KEY_ENTER)
            committed = True
        finally:
            if not committed:
                await self._abort_menu(start)
        state = await self._read_settled_state()
        if (now := state.setting("mode")) != mode:
            raise HomeAssistantError(f"Klydoclock switched to {now} instead of {mode}")
        return state

    async def _abort_menu(self, start: float) -> None:
        """Best effort: turn back to the entry the menu opened on and confirm it.

        Left open, the menu would fall back to FEED after about a minute.
        """
        try:
            await self._turn_menu_to(await self._menu_angle(), start)
            await self.adb.keyevent(KEY_ENTER)
        except (HomeAssistantError, KlydoConnectionError, KlydoRootError) as err:
            _LOGGER.warning("Could not close the Klydoclock home menu: %s", err)

    async def _navigate_to(self, klydo_id: str, mode: str | None) -> None:
        """Choose the list to walk, switch mode if needed, then walk it."""
        state = await self._read_settled_state()
        in_feed = klydo_id in state.feed
        in_favorites = klydo_id in state.favorites
        current = state.setting("mode")
        if mode == MODE_FEED and not in_feed:
            raise ServiceValidationError("This klydo is not in the clock's feed")
        if mode == MODE_FAVORITE and not in_favorites:
            raise ServiceValidationError("This klydo is not a favorite")
        if mode is None:
            if current == MODE_FAVORITE and in_favorites:
                mode = MODE_FAVORITE
            elif in_feed:
                mode = MODE_FEED
            elif in_favorites:
                mode = MODE_FAVORITE
            else:
                raise HomeAssistantError(
                    "This klydo is neither in the feed nor a favorite"
                )
        state = await self._switch_mode(state, mode)
        await self._walk_list(state, klydo_id, mode)

    async def _walk_list(self, state: KlydoState, klydo_id: str, mode: str) -> None:
        """Press next/previous until klydo_id is on display.

        In FEED mode the keys step through the feed, in FAVORITE mode through
        the favorites, both in list order.
        """
        presses = 0
        budget = len(state.feed) + 30
        wrap = True  # assume next wraps from the last entry to the first
        last_key: int | None = None
        flips = 0
        while state.klydo_id != klydo_id:
            if state.setting("mode") != mode:
                raise HomeAssistantError("The clock left the mode while navigating")
            items = state.feed if mode == MODE_FEED else state.favorites
            if klydo_id not in items:
                raise HomeAssistantError("The klydo is no longer in the list")
            if state.klydo_id not in items:
                raise HomeAssistantError(
                    "The klydo on display is not part of the list"
                )
            cur, tgt = items.index(state.klydo_id), items.index(klydo_id)
            forward = (tgt - cur) % len(items)
            backward = (cur - tgt) % len(items)
            if wrap:
                steps, key = (
                    (forward, KEY_NEXT)
                    if forward <= backward
                    else (backward, KEY_PREVIOUS)
                )
            elif tgt > cur:
                steps, key = tgt - cur, KEY_NEXT
            else:
                steps, key = cur - tgt, KEY_PREVIOUS
            if last_key is not None and key != last_key:
                flips += 1
                if flips >= 4:
                    raise HomeAssistantError(
                        "The clock keeps skipping past this klydo; giving up"
                    )
            last_key = key
            # After overshooting once, approach in single, settled steps.
            batch = 1 if flips else min(steps, NAV_BATCH)
            presses += batch
            if presses > budget:
                raise HomeAssistantError(
                    f"Klydo not reached after {presses} key presses"
                )
            await self.adb.shell("input keyevent " + " ".join([str(key)] * batch))
            before = state.klydo_id
            state = await self._read_settled_state()
            if state.klydo_id == before:
                if not wrap:
                    raise HomeAssistantError(
                        "Klydoclock did not react to the navigation keys"
                    )
                wrap = False  # maybe the feed does not wrap; go the direct way

    async def async_set_display_mode(self, target: str) -> None:
        """Press the sleep key until the display is in the wanted mode."""
        if target not in DISPLAY_MODES:
            raise HomeAssistantError(f"Unknown display mode: {target}")
        async with self._display_lock:
            try:
                await self._step_display_to(target)
            except UpdateFailed as err:
                raise HomeAssistantError(f"Klydoclock: {err}") from err
            finally:
                await self.async_refresh()

    async def _step_display_to(self, target: str) -> None:
        """Sleep-key stepping; the caller holds the display lock."""
        state = await self._async_update_data()
        # One full cycle is five presses; allow one spare.
        for _ in range(len(DISPLAY_MODES) + 1):
            if state.display_mode == target:
                return
            stamp = state.display_stamp
            await self.adb.keyevent(KEY_SLEEP)
            for _ in range(12):  # the app persists a change within ~0.3 s
                await asyncio.sleep(0.35)
                state = await self._async_update_data()
                if state.display_stamp != stamp:
                    break
            else:
                raise HomeAssistantError("Klydoclock did not react to the sleep key")
        raise HomeAssistantError(f"Klydoclock did not reach display mode {target}")

    @asynccontextmanager
    async def _awake(self, stay_awake: bool = False) -> AsyncIterator[None]:
        """Leave night mode for key navigation and return to it afterwards.

        In night mode the first key press only wakes the display and is
        otherwise swallowed. A cancelled job leaves the return to night mode
        to the job that replaced it; with stay_awake nobody returns to it.
        """
        state = await self._async_update_data()
        if state.display_mode == DISPLAY_OFF:
            raise HomeAssistantError("Klydoclock: the display is off")
        restore = True
        try:
            if state.display_mode == DISPLAY_NIGHT:
                self._night_pending = True
                await self.adb.keyevent(KEY_MENU)
                for _ in range(12):
                    await asyncio.sleep(0.5)
                    state = await self._async_update_data()
                    if state.display_mode != DISPLAY_NIGHT:
                        break
                else:
                    raise HomeAssistantError("Klydoclock did not leave night mode")
            yield
        except asyncio.CancelledError:
            restore = False
            raise
        finally:
            if stay_awake:
                self._night_pending = False
            elif restore and self._night_pending:
                try:
                    await self._step_display_to(DISPLAY_NIGHT)
                    self._night_pending = False
                except (HomeAssistantError, UpdateFailed) as err:
                    _LOGGER.warning("Klydoclock: could not return to night mode: %s", err)
