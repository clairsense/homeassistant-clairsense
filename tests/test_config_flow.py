"""Tests for the Clairsense config flow."""

from __future__ import annotations

from collections.abc import Generator
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from yarl import URL

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.clairsense.const import API_URL, DOMAIN, REVOKE_URL, TOKEN_URL

from .conftest import account_payload

REPO = Path(__file__).parent.parent
COMPONENT = REPO / "custom_components" / "clairsense"
REDIRECT = "https://my.home-assistant.io/redirect/oauth"
TOKEN = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.fixture
def my_component(hass: HomeAssistant) -> None:
    """Pretend the My Home Assistant redirect service is loaded."""
    hass.config.components.add("my")


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Setting up the entry is not under test here."""
    with patch(
        "custom_components.clairsense.async_setup_entry",
        new=AsyncMock(return_value=True),
    ) as mock:
        yield mock


async def _start_flow(hass: HomeAssistant, hass_client_no_auth, source=SOURCE_USER):
    assert await async_setup_component(hass, DOMAIN, {})
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source})


async def _finish_authorisation(
    hass: HomeAssistant, hass_client_no_auth, result: dict[str, Any]
) -> dict[str, Any]:
    """Play the browser: follow the callback with the state from the URL."""
    state = URL(result["url"]).query["state"]
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    return await hass.config_entries.flow.async_configure(result["flow_id"])


def _token_calls(aioclient_mock):
    return [c for c in aioclient_mock.mock_calls if str(c[1]) == TOKEN_URL]


def _revoke_calls(aioclient_mock):
    return [c[2] for c in aioclient_mock.mock_calls if str(c[1]) == REVOKE_URL]


NEW_TOKEN_REVOKED = [{"token": "new-refresh", "client_id": "home-assistant"}]


@pytest.mark.usefixtures("current_request_with_host", "my_component")
async def test_full_flow(hass, hass_client_no_auth, aioclient_mock):
    result = await _start_flow(hass, hass_client_no_auth)
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    url = URL(result["url"])
    assert str(url).startswith("https://smarthome.clairsense.net/oauth/authorize")
    assert url.query["client_id"] == "home-assistant"
    assert url.query["redirect_uri"] == REDIRECT
    assert url.query["code_challenge_method"] == "S256" and url.query["code_challenge"]

    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(API_URL, json=account_payload())
    result = await _finish_authorisation(hass, hass_client_no_auth, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Clairsense"
    assert result["result"].unique_id == "3f9a1c0b7d2e4a55"
    assert result["data"]["token"]["access_token"] == "new-access"
    (token_request,) = _token_calls(aioclient_mock)
    assert "client_secret" not in token_request[2]
    assert token_request[2]["code_verifier"]
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer new-access"


@pytest.mark.usefixtures("current_request_with_host", "my_component")
async def test_same_account_twice_gives_the_entry_the_new_token(
    hass, hass_client_no_auth, aioclient_mock, mock_setup_entry
):
    """The bridge keeps one grant, so the new sign-in replaced the entry's token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3f9a1c0b7d2e4a55",
        data={"auth_implementation": DOMAIN, "token": {"refresh_token": "old"}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert mock_setup_entry.call_count == 1

    result = await _start_flow(hass, hass_client_no_auth)
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.post(REVOKE_URL)
    aioclient_mock.get(API_URL, json=account_payload())
    result = await _finish_authorisation(hass, hass_client_no_auth, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["token"]["refresh_token"] == "new-refresh"
    assert entry.data["auth_implementation"] == DOMAIN
    assert mock_setup_entry.call_count == 2  # reloaded with the new token
    assert _revoke_calls(aioclient_mock) == []


@pytest.mark.usefixtures("current_request_with_host", "my_component")
@pytest.mark.parametrize("status", [503, 401])
async def test_api_failure_after_token_aborts(
    hass, hass_client_no_auth, aioclient_mock, status
):
    result = await _start_flow(hass, hass_client_no_auth)
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.post(REVOKE_URL)
    aioclient_mock.get(API_URL, status=status)
    result = await _finish_authorisation(hass, hass_client_no_auth, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert _revoke_calls(aioclient_mock) == NEW_TOKEN_REVOKED


@pytest.mark.usefixtures("current_request_with_host")
async def test_without_my_integration_aborts(hass, hass_client_no_auth):
    result = await _start_flow(hass, hass_client_no_auth)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "my_integration_required"


async def _reauth(hass, hass_client_no_auth, aioclient_mock, account_id):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3f9a1c0b7d2e4a55",
        data={"auth_implementation": DOMAIN, "token": {"access_token": "old"}},
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.post(REVOKE_URL)
    aioclient_mock.get(API_URL, json=account_payload(account_id=account_id))
    return entry, await _finish_authorisation(hass, hass_client_no_auth, result)


@pytest.mark.usefixtures("current_request_with_host", "my_component")
async def test_reauth_updates_token(hass, hass_client_no_auth, aioclient_mock):
    entry, result = await _reauth(
        hass, hass_client_no_auth, aioclient_mock, "3f9a1c0b7d2e4a55"
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"]["access_token"] == "new-access"
    assert entry.data["token"]["refresh_token"] == "new-refresh"


@pytest.mark.usefixtures("current_request_with_host", "my_component")
async def test_reauth_wrong_account_aborts(hass, hass_client_no_auth, aioclient_mock):
    entry, result = await _reauth(hass, hass_client_no_auth, aioclient_mock, "other")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["token"] == {"access_token": "old"}
    assert _revoke_calls(aioclient_mock) == NEW_TOKEN_REVOKED


@pytest.mark.usefixtures("current_request_with_host", "my_component")
async def test_reauth_as_another_set_up_account_gives_it_the_token(
    hass, hass_client_no_auth, aioclient_mock, mock_setup_entry
):
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="other",
        data={"auth_implementation": DOMAIN, "token": {"refresh_token": "other-old"}},
    )
    other.add_to_hass(hass)
    entry, result = await _reauth(hass, hass_client_no_auth, aioclient_mock, "other")
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["token"] == {"access_token": "old"}
    assert other.data["token"]["refresh_token"] == "new-refresh"
    assert other.data["auth_implementation"] == DOMAIN
    set_up = [call.args[1].entry_id for call in mock_setup_entry.call_args_list]
    assert set_up.count(other.entry_id) == 2  # set up, then reloaded with the token
    assert set_up.count(entry.entry_id) == 1
    assert _revoke_calls(aioclient_mock) == []


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth_without_my_integration_aborts(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3f9a1c0b7d2e4a55",
        data={"auth_implementation": DOMAIN, "token": {"access_token": "old"}},
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "my_integration_required"


def _keys(node: Any, prefix: str = "") -> set[str]:
    if isinstance(node, dict):
        return {k for key, v in node.items() for k in _keys(v, f"{prefix}{key}.")}
    return {prefix.rstrip(".")}


def test_translations_have_the_same_keys():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    for language in ("en", "tr"):
        translated = json.loads((COMPONENT / "translations" / f"{language}.json").read_text())
        assert _keys(translated) == _keys(strings), language
    assert json.loads((COMPONENT / "translations" / "en.json").read_text()) == strings


SCANNED_SUFFIXES = {".json", ".md", ".py", ".yml", ".yaml"}
# tests/ quotes the phrases on purpose; the rest is not part of the repository.
SKIPPED_TOP_DIRS = {"tests", ".venv", ".superpowers", ".git", ".pytest_cache"}


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(REPO):
        if Path(root) == REPO:
            dirs[:] = [d for d in dirs if d not in SKIPPED_TOP_DIRS]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        files += [Path(root) / n for n in names if Path(n).suffix in SCANNED_SUFFIXES]
    return files


def test_no_forbidden_wording():
    files = _scanned_files()
    suffixes = {p.suffix for p in files}
    assert {".json", ".md", ".py", ".yml"} <= suffixes
    text = "\n".join(p.read_text().lower() for p in files)
    for phrase in ("fire alarm", "fire detection", "yangın alarmı", "works with home assistant"):
        assert phrase not in text
