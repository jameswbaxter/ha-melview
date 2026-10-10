"""The MelView integration."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_LOCAL
from .coordinator import MelViewConfigEntry, MelViewCoordinator
from .melview import MelView, MelViewAuthentication, MelViewAuthError, MelViewError

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: MelViewConfigEntry) -> bool:
    """Log in, find the units, and start polling them."""
    # A session of its own: MelView's auth cookie is passed explicitly, but
    # this keeps its cookies out of HA's shared session all the same
    session = async_create_clientsession(hass)
    auth = MelViewAuthentication(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    try:
        await auth.async_login()
        devices = await MelView(
            session, auth, entry.data.get(CONF_LOCAL, False)
        ).async_get_devices_list()
    except MelViewAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except MelViewError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = MelViewCoordinator(hass, entry, devices)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MelViewConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
