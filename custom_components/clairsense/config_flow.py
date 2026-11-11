"""Config flow for Clairsense: sign in with a Clairsense account over OAuth2."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ClairsenseApiError, ClairsenseAuthError, async_get_account
from .const import DOMAIN


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the Clairsense sign-in."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return logging.getLogger(__name__)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the flow; the redirect goes through my.home-assistant.io."""
        if "my" not in self.hass.config.components:
            return self.async_abort(reason="my_integration_required")
        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Identify the account with the new token, then create or update the entry."""
        try:
            account = await async_get_account(
                async_get_clientsession(self.hass), data["token"]["access_token"]
            )
        except (ClairsenseApiError, ClairsenseAuthError):
            self.logger.exception("Could not read the Clairsense account")
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(account.account_id)

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Clairsense", data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the stored token stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to sign in again."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_pick_implementation(
            user_input={
                "implementation": self._get_reauth_entry().data["auth_implementation"]
            }
        )
