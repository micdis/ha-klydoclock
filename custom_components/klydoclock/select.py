"""Display mode selection for the Klydoclock."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DISPLAY_MODES
from .coordinator import KlydoConfigEntry
from .entity import KlydoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlydoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entities."""
    async_add_entities([KlydoDisplayModeSelect(entry.runtime_data, "display_mode")])


class KlydoDisplayModeSelect(KlydoEntity, SelectEntity):
    """The stage of the sleep-key cycle: three brightness levels, red, off."""

    _attr_options = DISPLAY_MODES

    @property
    def current_option(self) -> str | None:
        """Return the current display mode."""
        return self.coordinator.data.display_mode

    async def async_select_option(self, option: str) -> None:
        """Step the clock to the selected display mode."""
        await self.coordinator.async_set_display_mode(option)
