"""Display on/off switch for the Klydoclock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DISPLAY_BRIGHT, DISPLAY_OFF
from .coordinator import KlydoConfigEntry
from .entity import KlydoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlydoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch entities."""
    async_add_entities([KlydoDisplaySwitch(entry.runtime_data, "display")])


class KlydoDisplaySwitch(KlydoEntity, SwitchEntity):
    """Turns the display off and back on (to full brightness)."""

    @property
    def is_on(self) -> bool | None:
        """Return whether the display shows anything."""
        mode = self.coordinator.data.display_mode
        return None if mode is None else mode != DISPLAY_OFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the display on; a display that is already on is left as it is."""
        if self.coordinator.data.display_mode == DISPLAY_OFF or not self.is_on:
            await self.coordinator.async_set_display_mode(DISPLAY_BRIGHT)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the display off."""
        await self.coordinator.async_set_display_mode(DISPLAY_OFF)
