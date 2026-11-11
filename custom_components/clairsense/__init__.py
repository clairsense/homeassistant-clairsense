"""The Clairsense integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import async_revoke_token
from .const import AUTHORIZE_URL, CLIENT_ID, DOMAIN, TOKEN_URL
from .coordinator import ClairsenseConfigEntry, ClairsenseCoordinator

__all__ = ["ClairsenseConfigEntry", "async_setup_entry", "async_unload_entry"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR]


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


async def async_setup_entry(hass: HomeAssistant, entry: ClairsenseConfigEntry) -> bool:
    """Set up Clairsense from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    coordinator = ClairsenseCoordinator(hass, entry, session)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClairsenseConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ClairsenseConfigEntry) -> None:
    """Revoke the refresh token when the entry is removed; never block removal."""
    refresh_token = entry.data.get("token", {}).get("refresh_token")
    if refresh_token:
        await async_revoke_token(async_get_clientsession(hass), refresh_token)
