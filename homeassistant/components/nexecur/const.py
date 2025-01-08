"""Constants for the Nexecur Alarm integration."""

import logging

DOMAIN = "nexecur"

API_TOKEN_URL = (
    "https://sso.xiotnxc.com/auth/realms/nx-realm/protocol/openid-connect/token"
)
API_CLIENT_ID = "nx-api"
API_CLIENT_SECRET = "e614f1e4-959d-4d64-859b-5d420b579850"
API_BASE_URL = "https://web.maprotectionmaison.fr"

LOGGER = logging.getLogger(DOMAIN)
CONF_PHONE_ID = "phone_id"
CONF_SITE_ID = "site_id"
REFRESH_TOKEN_OUT_OF_SYNC_MAX_SEC = 20
