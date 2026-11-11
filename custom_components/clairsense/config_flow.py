"""Config flow for Clairsense: sign in with a Clairsense account over OAuth2."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ClairsenseApiError,
    ClairsenseAuthError,
    async_get_account,
    async_revoke_token,
)
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
        if not self._my_integration_loaded():
            return self.async_abort(reason="my_integration_required")
        return await super().async_step_user(user_input)

    def _my_integration_loaded(self) -> bool:
        """Signing in returns to Home Assistant through the My redirect."""
        return "my" in self.hass.config.components

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Identify the account with the new token, then create or update the entry.

        The bridge keeps one grant per account and client, so the token just
        issued has replaced any earlier one: it must end up in an entry or be
        revoked, never dropped.
        """
        session = async_get_clientsession(self.hass)
        try:
            account = await async_get_account(session, data["token"]["access_token"])
        except (ClairsenseApiError, ClairsenseAuthError):
            self.logger.exception("Could not read the Clairsense account")
            await async_revoke_token(session, data["token"]["refresh_token"])
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(account.account_id)

        if self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            if reauth_entry.unique_id != account.account_id:
                await self._async_hand_token_to_entry_or_revoke(
                    account.account_id, data
                )
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(reauth_entry, data=data)

        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(title="Clairsense", data=data)

    async def _async_hand_token_to_entry_or_revoke(
        self, account_id: str, data: dict[str, Any]
    ) -> None:
        """Give the token to the entry of the account it belongs to, else revoke it."""
        other = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, account_id
        )
        if other is not None and other.source != SOURCE_IGNORE:
            self.hass.config_entries.async_update_entry(
                other, data={**other.data, **data}
            )
            self.hass.config_entries.async_schedule_reload(other.entry_id)
            return
        await async_revoke_token(
            async_get_clientsession(self.hass), data["token"]["refresh_token"]
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the stored token stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to sign in again.

        The form is shown even without the My integration, so the request stays
        visible; the check happens when the user goes on to sign in.
        """
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        if not self._my_integration_loaded():
            return self.async_abort(reason="my_integration_required")
        return await self.async_step_pick_implementation(
            user_input={
                "implementation": self._get_reauth_entry().data["auth_implementation"]
            }
        )
