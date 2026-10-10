"""Sensors for the Klydoclock."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KlydoConfigEntry, KlydoCoordinator, KlydoState
from .entity import KlydoEntity


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _klydo_name(state: KlydoState) -> str | None:
    if state.klydo is not None:
        return state.klydo.name
    return state.klydo_id


def _klydo_attributes(state: KlydoState) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "klydo_id": state.klydo_id,
        "favorite": state.is_favorite,
        "changed": state.changed("klydo"),
    }
    if state.klydo is not None:
        attrs["main_loop"] = state.klydo.main_loop
        attrs["artist"] = state.artist
        attrs["creator_id"] = state.klydo.creator
        if state.klydo.subtitle:
            attrs["subtitle"] = state.klydo.subtitle
    if state.klydo_id in state.feed:
        attrs["feed_position"] = state.feed.index(state.klydo_id) + 1
    attrs["feed_size"] = len(state.feed)
    return attrs


@dataclass(frozen=True, kw_only=True)
class KlydoSensorDescription(SensorEntityDescription):
    """Describes a Klydoclock sensor."""

    value_fn: Callable[[KlydoState], Any]
    attributes_fn: Callable[[KlydoState], dict[str, Any]] | None = None


SENSORS: tuple[KlydoSensorDescription, ...] = (
    KlydoSensorDescription(
        key="klydo", value_fn=_klydo_name, attributes_fn=_klydo_attributes
    ),
    KlydoSensorDescription(key="artist", value_fn=lambda s: s.artist),
    KlydoSensorDescription(
        key="brightness_level", value_fn=lambda s: _int(s.setting("brightness"))
    ),
    KlydoSensorDescription(
        key="favorites",
        value_fn=lambda s: len(s.favorites),
        attributes_fn=lambda s: {
            "klydo_ids": s.favorites,
            "klydo_names": s.favorite_names,
        },
    ),
    KlydoSensorDescription(
        key="screen_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.setting("screenState"),
    ),
    KlydoSensorDescription(
        key="night_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.setting("nightMode"),
        attributes_fn=lambda s: {"appearance": s.setting("nightModeAppearance")},
    ),
    KlydoSensorDescription(
        key="mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.setting("mode"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlydoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(KlydoSensor(entry.runtime_data, desc) for desc in SENSORS)


class KlydoSensor(KlydoEntity, SensorEntity):
    """A value read from the clock's settings store."""

    entity_description: KlydoSensorDescription

    def __init__(
        self, coordinator: KlydoCoordinator, description: KlydoSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
