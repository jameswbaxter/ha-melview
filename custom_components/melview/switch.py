"""Zone switches for ducted MelView units."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MelViewConfigEntry, MelViewCoordinator
from .entity import MelViewEntity
from .melview import MelViewDevice, MelViewError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MelViewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a switch per zone, for the units that have zones."""
    coordinator = entry.runtime_data
    async_add_entities(
        MelViewZoneSwitch(coordinator, device, zone.id, zone.name)
        for device in coordinator.devices
        for zone in device.get_zones()
    )


class MelViewZoneSwitch(MelViewEntity, SwitchEntity):
    """One zone of a ducted unit."""

    def __init__(
        self, coordinator: MelViewCoordinator, device: MelViewDevice, zoneid: int, name: str
    ) -> None:
        super().__init__(coordinator, device)
        self._zoneid = zoneid
        self._attr_name = f"{name} zone"
        self._attr_unique_id = f"{device.get_id()}-{zoneid}"

    @property
    def available(self) -> bool:
        return super().available and self._device.get_zone(self._zoneid) is not None

    @property
    def is_on(self) -> bool | None:
        zone = self._device.get_zone(self._zoneid)
        return zone.status == 1 if zone else None

    async def _set(self, on: bool) -> None:
        try:
            await self._device.async_set_zone(self._zoneid, on)
        except MelViewError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
