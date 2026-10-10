"""Base entity for MelView units."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MelViewCoordinator
from .melview import MelViewDevice


class MelViewEntity(CoordinatorEntity[MelViewCoordinator]):
    """An entity of one MelView unit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MelViewCoordinator, device: MelViewDevice) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.get_id())},
            name=device.get_friendly_name(),
            manufacturer="Mitsubishi Electric",
            model="MelView Wi-Fi Control",
        )
