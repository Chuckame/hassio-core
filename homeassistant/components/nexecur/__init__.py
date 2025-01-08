"""The Nexecur Alarm integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import NexecurApi, NexecurTokenManager
from .coordinator import NexecurCoordinator

PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL]


@dataclass
class NexecurData:
    """Config Entry global data."""

    api: NexecurApi
    coordinator: NexecurCoordinator


type NexecurConfigEntry = ConfigEntry[NexecurData]


async def async_setup_entry(hass: HomeAssistant, entry: NexecurConfigEntry) -> bool:
    """Set up Nexecur Alarm from a config entry."""

    api = NexecurApi(
        aiohttp_client.async_get_clientsession(hass),
        NexecurTokenManager(
            hass,
            username=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
        ),
    )

    coordinator = NexecurCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = NexecurData(api, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NexecurConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
