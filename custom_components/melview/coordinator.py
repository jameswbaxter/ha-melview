"""Polls MelView for every unit on the account."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .melview import MelViewAuthError, MelViewDevice, MelViewError

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)

type MelViewConfigEntry = ConfigEntry[MelViewCoordinator]


class MelViewCoordinator(DataUpdateCoordinator[None]):
    """Refreshes every unit; the entities read from the units' caches."""

    def __init__(
        self, hass: HomeAssistant, entry: MelViewConfigEntry, devices: list[MelViewDevice]
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.devices = devices

    async def _async_update_data(self) -> None:
        try:
            for device in self.devices:
                await device.async_refresh()
        except MelViewAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MelViewError as err:
            raise UpdateFailed(str(err)) from err
