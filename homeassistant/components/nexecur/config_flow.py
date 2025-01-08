"""Config flow for the Nexecur integration."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NexecurApi, NexecurSite, NexecurTokenManager
from .const import CONF_PHONE_ID, CONF_SITE_ID, DOMAIN, LOGGER

STEP_USER_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class NexecurConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nexecur."""

    VERSION = 1

    _register_phone_task: asyncio.Task | None = None
    _api: NexecurApi | None = None
    _sites: list[NexecurSite] | None = None
    _site_id: str | None = None
    _site_name: str | None = None
    _phone_id: str | None = None
    _username: str | None = None
    _password: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        LOGGER.info("Starting config flow")

        # creds step
        if not user_input:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_CREDENTIALS_SCHEMA,
            )
        try:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            tokenManager = NexecurTokenManager(
                self.hass,
                username=email,
                password=password,
            )
            await tokenManager.async_get_valid_access_token()
            self._username = email
            self._password = password
            self._api = NexecurApi(
                httpClient=async_get_clientsession(self.hass),
                tokenManager=tokenManager,
            )
        except ClientError as exception:
            LOGGER.error("Could not connect to Nexecur API: %s", exception)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_CREDENTIALS_SCHEMA,
                errors={"base": "invalid_auth"},
            )
        return await self.async_step_select_site()

    async def async_step_select_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the site selection step."""
        LOGGER.info("Selecting site")
        # site step if more than 1 site
        if not user_input:
            assert self._api
            sites = await self._api.get_sites()
            if len(sites) == 0:
                return self.async_abort(reason="no_sites")
            if len(sites) > 1:
                self._sites = sites
                return self.async_show_form(
                    step_id="select_site",
                    data_schema=self._get_sites_schema(sites),
                )
            # When only 1 site, automatically select it
            self._site_id = sites[0].id
            self._site_name = sites[0].name
        else:
            self._site_id = user_input[CONF_SITE_ID]
            assert self._sites
            self._site_name = next(
                site.name for site in self._sites if site.id == self._site_id
            )

        await self.async_set_unique_id(self._site_id)
        self._abort_if_unique_id_configured()

        return await self.async_step_register_phone()

    async def async_step_register_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the phone registration step."""
        LOGGER.info("Registering phone")
        self._phone_id = self.flow_id

        assert self._api
        assert self._site_id
        if await self._api.is_phone_registered(
            phone_id=self._phone_id, site_id=self._site_id
        ):
            LOGGER.info("Phone %s already registered", self._phone_id)
            return await self.async_step_finish()

        async def _wait_for_registering_ok() -> None:
            LOGGER.debug("Sending sms to register Home Assistant")
            assert self._api
            assert self._phone_id
            assert self._site_id
            await self._api.register_phone(
                self._phone_id, "Home Assistant", "Home Assistant"
            )
            LOGGER.debug("Checking if phone is registered for a maximum of 60 seconds")
            async with asyncio.timeout(60):
                # A bit of a hack to wait for the phone to be registered
                # if registered too quickly, the UI will be stuck
                await asyncio.sleep(3)

                while not await self._api.is_phone_registered(
                    self._phone_id, self._site_id
                ):
                    await asyncio.sleep(3)
                LOGGER.debug("Registered !")

        if not self._register_phone_task:
            self._register_phone_task = self.hass.async_create_task(
                _wait_for_registering_ok(), eager_start=False
            )

        if not self._register_phone_task.done():
            return self.async_show_progress(
                step_id="register_phone",
                progress_action="waiting_for_registration",
                progress_task=self._register_phone_task,
            )
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the site selection step."""
        LOGGER.info("Finishing config flow")

        assert self._register_phone_task
        if self._register_phone_task.exception():
            LOGGER.error(
                "Error while registering Home Assistant: %s",
                self._register_phone_task.exception(),
            )
            return self.async_abort(reason="phone_registration_error")

        assert self._phone_id
        assert self._username
        assert self._password
        return self.async_create_entry(
            title=f"Nexecur ({self._site_name})",
            data={
                CONF_SITE_ID: self._site_id,
                CONF_PHONE_ID: self._phone_id,
                CONF_EMAIL: self._username,
                CONF_PASSWORD: self._password,
            },
        )

    async def async_step_phone_registration_error(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the phone registration error step."""

        assert self._register_phone_task
        return self.async_abort(
            reason=f"Error while registering Home Assistant: {self._register_phone_task.exception()}"
        )

    def _get_sites_schema(self, sites: list[NexecurSite]) -> vol.Schema:
        """Get the schema for selecting a site."""
        LOGGER.info("Got sites: %s", sites)
        return vol.Schema(
            {
                vol.Required(CONF_SITE_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=site.id, label=site.name)
                            for site in sites
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
