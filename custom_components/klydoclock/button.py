"""Buttons that replay the remote control keys."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb import KlydoConnectionError, KlydoRootError
from .const import (
    KEY_FAVORITE,
    KEY_INFO,
    KEY_NEXT,
    KEY_PREVIOUS,
    KEY_SETTINGS,
    KEY_SLEEP,
)
from .coordinator import KlydoConfigEntry, KlydoCoordinator
from .entity import KlydoEntity

BUTTONS: dict[str, int] = {
    "next": KEY_NEXT,
    "previous": KEY_PREVIOUS,
    "toggle_favorite": KEY_FAVORITE,
    "info": KEY_INFO,
    "settings": KEY_SETTINGS,
    "sleep": KEY_SLEEP,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlydoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities(
        KlydoKeyButton(entry.runtime_data, key, keycode)
        for key, keycode in BUTTONS.items()
    )


class KlydoKeyButton(KlydoEntity, ButtonEntity):
    """One key of the remote."""

    def __init__(self, coordinator: KlydoCoordinator, key: str, keycode: int) -> None:
        super().__init__(coordinator, key)
        self._keycode = keycode

    async def async_press(self) -> None:
        """Send the key to the clock."""
        try:
            await self.coordinator.async_press_key(self._keycode)
        except (KlydoConnectionError, KlydoRootError) as err:
            raise HomeAssistantError(f"Klydoclock: {err}") from err
