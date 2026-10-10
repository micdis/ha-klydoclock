"""Display mode and favorite selection for the Klydoclock."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    async_add_entities(
        [
            KlydoDisplayModeSelect(entry.runtime_data, "display_mode"),
            KlydoFavoriteSelect(entry.runtime_data, "favorite_klydo"),
        ]
    )


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


class KlydoFavoriteSelect(KlydoEntity, SelectEntity):
    """Pick one of the favorites; the clock walks the feed to it."""

    @property
    def options(self) -> list[str]:
        """Return the names of the favorites."""
        return self.coordinator.data.favorite_names

    @property
    def current_option(self) -> str | None:
        """Return the current klydo if it is a favorite."""
        state = self.coordinator.data
        if state.klydo_id in state.favorites:
            return state.favorite_names[state.favorites.index(state.klydo_id)]
        return None

    async def async_select_option(self, option: str) -> None:
        """Navigate the clock to the selected favorite."""
        state = self.coordinator.data
        if option not in state.favorite_names:
            raise HomeAssistantError(f"'{option}' is not a favorite")
        klydo_id = state.favorites[state.favorite_names.index(option)]
        await self.coordinator.async_show_klydo(klydo_id)
