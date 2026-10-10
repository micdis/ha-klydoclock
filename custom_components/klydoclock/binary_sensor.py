"""Binary sensors for the Klydoclock."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KlydoConfigEntry
from .entity import KlydoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlydoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities([KlydoFavoriteSensor(entry.runtime_data, "favorite")])


class KlydoFavoriteSensor(KlydoEntity, BinarySensorEntity):
    """On while the klydo on display is one of the favorites."""

    @property
    def is_on(self) -> bool | None:
        """Return whether the current klydo is a favorite."""
        return self.coordinator.data.is_favorite
