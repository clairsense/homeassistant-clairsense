"""Tests for the Clairsense API client."""

from __future__ import annotations

import asyncio

import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.clairsense.api import (
    ClairsenseApiError,
    ClairsenseAuthError,
    async_get_account,
)
from custom_components.clairsense.const import API_URL

from .conftest import account_payload


async def test_parses_account(hass, aioclient_mock):
    aioclient_mock.get(API_URL, json=account_payload())
    account = await async_get_account(async_get_clientsession(hass), "tok")
    device = account.devices["CS-A"]
    assert account.account_id == "3f9a1c0b7d2e4a55"
    assert (device.name, device.room, device.online) == ("Living room", "Salon", True)
    assert device.firmware == "1.0.3"
    assert device.readings == {"temperature": 22.4, "co2": 612}
    assert isinstance(device.readings["co2"], int)
    assert isinstance(device.readings["temperature"], float)
    assert device.last_seen.tzinfo is not None
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer tok"


async def test_unknown_reading_is_ignored(hass, aioclient_mock):
    aioclient_mock.get(
        API_URL, json=account_payload(readings={"co2": 600, "voc_index": 104})
    )
    account = await async_get_account(async_get_clientsession(hass), "tok")
    assert account.devices["CS-A"].readings == {"co2": 600}


@pytest.mark.parametrize("bad", ["high", None, True, [1], {"v": 1}])
async def test_non_numeric_reading_is_ignored(hass, aioclient_mock, bad):
    aioclient_mock.get(
        API_URL, json=account_payload(readings={"co2": bad, "temperature": 21.0})
    )
    account = await async_get_account(async_get_clientsession(hass), "tok")
    assert account.devices["CS-A"].readings == {"temperature": 21.0}


async def test_offline_device(hass, aioclient_mock):
    aioclient_mock.get(API_URL, json=account_payload(online=False))
    account = await async_get_account(async_get_clientsession(hass), "tok")
    device = account.devices["CS-A"]
    assert device.online is False
    assert device.readings == {}
    assert device.last_seen is None


async def test_401_raises_auth_error(hass, aioclient_mock):
    aioclient_mock.get(API_URL, status=401)
    with pytest.raises(ClairsenseAuthError):
        await async_get_account(async_get_clientsession(hass), "tok")


async def test_503_raises_api_error(hass, aioclient_mock):
    aioclient_mock.get(API_URL, status=503)
    with pytest.raises(ClairsenseApiError):
        await async_get_account(async_get_clientsession(hass), "tok")


async def test_timeout_raises_api_error(hass, aioclient_mock):
    aioclient_mock.get(API_URL, exc=asyncio.TimeoutError)
    with pytest.raises(ClairsenseApiError):
        await async_get_account(async_get_clientsession(hass), "tok")


async def test_connection_error_raises_api_error(hass, aioclient_mock):
    import aiohttp

    aioclient_mock.get(API_URL, exc=aiohttp.ClientConnectionError)
    with pytest.raises(ClairsenseApiError):
        await async_get_account(async_get_clientsession(hass), "tok")


@pytest.mark.parametrize(
    "body",
    [
        {"devices": "nope", "account_id": "x"},
        {"devices": []},
        {"account_id": "x", "devices": [{"name": "no id"}]},
        {"account_id": "x", "devices": ["str"]},
        ["not", "a", "dict"],
    ],
)
async def test_malformed_body_raises_api_error(hass, aioclient_mock, body):
    aioclient_mock.get(API_URL, json=body)
    with pytest.raises(ClairsenseApiError):
        await async_get_account(async_get_clientsession(hass), "tok")


async def test_non_json_body_raises_api_error(hass, aioclient_mock):
    aioclient_mock.get(API_URL, text="<html>")
    with pytest.raises(ClairsenseApiError):
        await async_get_account(async_get_clientsession(hass), "tok")
