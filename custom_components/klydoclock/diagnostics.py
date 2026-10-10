"""Diagnostics for the Klydoclock integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import KlydoConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KlydoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    state = coordinator.data
    settings = dict(state.settings)
    # The raw feed list is reflected in feed_size / feed_position already.
    settings.pop("feeds_value", None)
    return {
        "app_version": coordinator.app_version,
        "catalog_size": len(coordinator.catalog),
        "artists_cached": len(coordinator.artists),
        "klydo_id": state.klydo_id,
        "klydo_name": state.klydo.name if state.klydo else None,
        "favorites": state.favorites,
        "favorite_names": state.favorite_names,
        "feed_size": len(state.feed),
        "feed_position": (
            state.feed.index(state.klydo_id) + 1
            if state.klydo_id in state.feed
            else None
        ),
        "settings": settings,
    }
