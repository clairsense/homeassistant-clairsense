"""The Clairsense integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import AUTHORIZE_URL, CLIENT_ID, DOMAIN, TOKEN_URL

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the OAuth2 implementation: authorisation code with PKCE, no secret."""
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce(
            hass, DOMAIN, CLIENT_ID, AUTHORIZE_URL, TOKEN_URL
        ),
    )
    return True
