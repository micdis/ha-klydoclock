"""Base entity for the Klydoclock."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KlydoCoordinator


class KlydoEntity(CoordinatorEntity[KlydoCoordinator]):
    """Entity bound to one clock."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KlydoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        serial = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=entry.title,
            manufacturer="Klydo",
            model="Klydoclock",
            sw_version=coordinator.app_version,
            configuration_url=None,
        )
