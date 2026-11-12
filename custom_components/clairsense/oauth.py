"""The Clairsense sign-in method: authorisation code with PKCE, no client secret."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow

from .const import AUTHORIZE_URL, CLIENT_ID, DOMAIN, TOKEN_URL


@callback
def async_ensure_implementation(hass: HomeAssistant) -> None:
    """Register the sign-in method, once per Home Assistant run.

    Two callers need it. async_setup, for entries that already exist. And the
    config flow, because for a first sign-in Home Assistant loads only the
    config flow module and never runs async_setup; without this the flow stops
    with "not configured". Registering once keeps a single PKCE verifier, so a
    flow in progress is not cut off by a second caller.
    """
    registered = hass.data.get(config_entry_oauth2_flow.DATA_IMPLEMENTATIONS, {})
    if DOMAIN in registered.get(DOMAIN, {}):
        return
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce(
            hass, DOMAIN, CLIENT_ID, AUTHORIZE_URL, TOKEN_URL
        ),
    )
