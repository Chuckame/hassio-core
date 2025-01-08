"""Coordinator for fetching data from fitbit API."""

import asyncio
import datetime
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import NexecurConfigEntry
from .api import NexecurAlarmStateEnum, NexecurApi
from .const import CONF_PHONE_ID, CONF_SITE_ID, DOMAIN, LOGGER

UPDATE_INTERVAL: Final = datetime.timedelta(seconds=15)
TIMEOUT = 10


class NexecurCoordinator(DataUpdateCoordinator[NexecurAlarmStateEnum]):
    """Coordinator for fetching nexecur state from the API."""

    def __init__(
        self, hass: HomeAssistant, api: NexecurApi, config_entry: NexecurConfigEntry
    ) -> None:
        """Initialize NexecurDeviceCoordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
            config_entry=config_entry,
        )
        self.api = api

    async def _async_update_data(self) -> NexecurAlarmStateEnum:
        """Fetch data from API endpoint."""

        assert self.config_entry
        phone_id = self.config_entry.data[CONF_PHONE_ID]
        site_id = self.config_entry.data[CONF_SITE_ID]

        if not phone_id or not site_id:
            raise ConfigEntryError(
                f"Missing {CONF_PHONE_ID} or {CONF_SITE_ID} in config entry data"
            )

        async with asyncio.timeout(TIMEOUT):
            return await self.api.get_alarm_state(
                phone_id=phone_id,
                site_id=site_id,
            )
