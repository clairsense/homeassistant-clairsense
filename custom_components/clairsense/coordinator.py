"""Coordinator that polls the Clairsense account."""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Account,
    ClairsenseApiError,
    ClairsenseAuthError,
    Device,
    async_get_account,
)
from .const import DOMAIN, MANUFACTURER, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type ClairsenseConfigEntry = ConfigEntry[ClairsenseCoordinator]

# The token endpoint answers these when the refresh token is no longer usable.
_REAUTH_STATUSES = (400, 401)


def device_info_for(device: Device) -> DeviceInfo:
    """Describe a monitor; shared by the device registry sync and the entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, device.id)},
        name=device.name,
        manufacturer=MANUFACTURER,
        sw_version=device.firmware,
        suggested_area=device.room,
    )


class ClairsenseCoordinator(DataUpdateCoordinator[Account]):
    """Fetch the account every minute; devices follow the account."""

    config_entry: ClairsenseConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ClairsenseConfigEntry,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._oauth_session = oauth_session
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> Account:
        try:
            await self._oauth_session.async_ensure_token_valid()
        except aiohttp.ClientResponseError as err:
            if err.status in _REAUTH_STATUSES:
                raise ConfigEntryAuthFailed("Sign-in was rejected") from err
            raise UpdateFailed(f"Token refresh failed: {err.status}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Token refresh failed: {err}") from err

        token = self.config_entry.data["token"]["access_token"]
        try:
            account = await async_get_account(self._session, token)
        except ClairsenseAuthError as err:
            raise ConfigEntryAuthFailed("Access token rejected") from err
        except ClairsenseApiError as err:
            raise UpdateFailed(str(err)) from err

        # Only a successful fetch gets here, so a failed poll never removes anything.
        self._sync_devices(account)
        return account

    def _sync_devices(self, account: Account) -> None:
        """Register the account's devices and drop the ones that are gone."""
        registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id
        for device in account.devices.values():
            registry.async_get_or_create(
                config_entry_id=entry_id, **device_info_for(device)
            )
        for stale in dr.async_entries_for_config_entry(registry, entry_id):
            ids = {i[1] for i in stale.identifiers if i[0] == DOMAIN}
            if ids and not ids & account.devices.keys():
                registry.async_update_device(
                    stale.id, remove_config_entry_id=entry_id
                )
