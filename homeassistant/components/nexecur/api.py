"""HTTP Client for Nexecur API."""

from asyncio import Lock
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError
import time
from typing import Any, cast

from aiohttp import ClientError, ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    API_CLIENT_ID,
    API_CLIENT_SECRET,
    API_TOKEN_URL,
    DOMAIN,
    LOGGER,
    REFRESH_TOKEN_OUT_OF_SYNC_MAX_SEC,
)


@dataclass(frozen=True)
class NexecurSite:
    """Represent a site where a nexecur alarm is."""

    name: str
    id: str


class NexecurAlarmStateEnum(StrEnum):
    """Represent the possible states of a nexecur alarm."""

    ACTIVE = "ACTIVE"
    NIGHT = "NIGHT"
    INACTIVE = "INACTIVE"


class NexecurTokenManager:
    """Manage to renew the access token using the refresh token or user/password when refresh not possible."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Initialize the token manager."""
        self._hass = hass
        self._username = username
        self._password = password
        self._token_lock = Lock()
        self._token: dict[Any, Any] | None = None

    def is_token_valid(self) -> bool:
        """Return if token is still valid."""
        assert self._token
        return time.time() + REFRESH_TOKEN_OUT_OF_SYNC_MAX_SEC < cast(
            float, self._token["expires_at"]
        )

    async def async_get_valid_access_token(self) -> str:
        """Ensure that the current token is valid."""
        async with self._token_lock:
            if self._token is None:
                self._token = await self._async_create_token()
            if not self.is_token_valid():
                LOGGER.info("Token expired, refreshing. Token: %s", self._token)
                try:
                    self._token = await self._async_refresh_token()
                except ClientError:
                    self._token = await self._async_create_token()
            return self._token["access_token"]

    async def _async_create_token(self) -> dict:
        """Create a new token from stored username and password."""
        return await self._token_request(
            {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            }
        )

    async def _async_refresh_token(self) -> dict:
        """Refresh tokens. Use first the refresh token, then the password (generally needed each month)."""
        assert self._token
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": self._token["refresh_token"],
            }
        )

    async def _token_request(self, data: dict) -> dict:
        """Make a token request."""
        session = async_get_clientsession(self._hass)

        data["client_id"] = API_CLIENT_ID
        data["client_secret"] = API_CLIENT_SECRET

        LOGGER.debug("Sending token request to %s", API_TOKEN_URL)
        resp = await session.post(API_TOKEN_URL, data=data)
        if resp.status >= 400:
            try:
                error_response = await resp.json()
            except (ClientError, JSONDecodeError):
                error_response = {}
            error_code = error_response.get("error", "unknown")
            error_description = error_response.get("error_description", "unknown error")
            LOGGER.error(
                "Token request for %s failed with status %s (%s): %s",
                DOMAIN,
                resp.status,
                error_code,
                error_description,
            )
        resp.raise_for_status()
        token = cast(dict, await resp.json())
        token["expires_at"] = time.time() + cast(int, token["expires_in"])
        return token


class NexecurApi:
    """Provide a typed access to the Nexecur http API."""

    def __init__(
        self, httpClient: ClientSession, tokenManager: NexecurTokenManager
    ) -> None:
        """Initialize NexecurApi."""
        self._httpClient = httpClient
        self._tokenManager = tokenManager

    async def get_sites(self) -> list[NexecurSite]:
        """Return the sites linked to the account."""
        url = f"{API_BASE_URL}/sites?webRequest=true"
        async with self._httpClient.get(
            url,
            headers={
                "Authorization": f"Bearer {await self._tokenManager.async_get_valid_access_token()}",
                "Content-Type": "application/json",
            },
        ) as response:
            response.raise_for_status()
            sites_data = await response.json()
            return [
                NexecurSite(
                    name=site.get("name"),
                    id=site.get("siteId"),
                )
                for site in sites_data
            ]

    async def is_phone_registered(self, phone_id: str, site_id: str) -> bool:
        """Return whether the phone is registered to the account."""
        url = f"{API_BASE_URL}/sites/{site_id}"
        async with self._httpClient.get(
            url,
            headers={
                "telId": phone_id,
                "Authorization": f"Bearer {await self._tokenManager.async_get_valid_access_token()}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status == 403:
                return False
            response.raise_for_status()
            return True

    async def get_alarm_state(
        self, phone_id: str, site_id: str
    ) -> NexecurAlarmStateEnum:
        """Return the state of the site's alarm."""
        url = f"{API_BASE_URL}/sites/{site_id}/state"
        async with self._httpClient.get(
            url,
            headers={
                "telId": phone_id,
                "Authorization": f"Bearer {await self._tokenManager.async_get_valid_access_token()}",
                "Content-Type": "application/json",
            },
        ) as response:
            response.raise_for_status()
            site_state = await response.json()
            site_state = site_state.get("siteState")
            state_mapping = {
                "INACTIV": NexecurAlarmStateEnum.INACTIVE,
                "ACTIV": NexecurAlarmStateEnum.ACTIVE,  # codespell:ignore
                "NIGHT": NexecurAlarmStateEnum.NIGHT,
            }
            try:
                return state_mapping[site_state]
            except KeyError:
                raise ValueError(f"Invalid site state: {site_state}") from None

    async def set_alarm_state(
        self,
        phone_id: str,
        site_id: str,
        state: NexecurAlarmStateEnum,
    ) -> None:
        """Set the state of the site's alarm."""
        url = f"{API_BASE_URL}/sites/{site_id}/state"
        payload = {"position": state}
        async with self._httpClient.put(
            url,
            headers={
                "telId": phone_id,
                "Authorization": f"Bearer {await self._tokenManager.async_get_valid_access_token()}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as response:
            response.raise_for_status()

    async def register_phone(
        self, phone_id: str, phone_model: str, phone_name: str
    ) -> None:
        """Register a new phone to the account. It will send a SMS to the phone containing a link to allow the phone to interact with Nexecur."""
        url = f"{API_BASE_URL}/phone-authorization/ask-authorization"

        payload = {
            "phoneId": phone_id,
            "modele": phone_model,
            "phoneName": phone_name,
        }
        headers = {
            "branding": "CA",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {await self._tokenManager.async_get_valid_access_token()}",
        }

        async with self._httpClient.post(
            url, headers=headers, json=payload
        ) as response:
            response.raise_for_status()
