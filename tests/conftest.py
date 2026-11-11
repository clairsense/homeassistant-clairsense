"""Shared fixtures for the Clairsense tests."""

from __future__ import annotations

import time
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.clairsense.const import API_URL, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components."""


def account_payload(
    *,
    account_id: str = "3f9a1c0b7d2e4a55",
    readings: dict[str, Any] | None = None,
    online: bool = True,
    devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a valid API body; by default one online device, CS-A."""
    if devices is None:
        devices = [
            {
                "id": "CS-A",
                "name": "Living room",
                "room": "Salon",
                "firmware": "1.0.3",
                "online": online,
                "last_seen": "2026-11-11T09:30:00Z" if online else None,
                "readings": (
                    {"temperature": 22.4, "co2": 612} if readings is None else readings
                )
                if online
                else {},
            }
        ]
    return {"account_id": account_id, "devices": devices}


def token_data(*, expires_in: float = 3600, access: str = "access-1", refresh: str = "refresh-1") -> dict[str, Any]:
    """Return a stored OAuth token; a negative expires_in makes it expired."""
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "expires_at": time.time() + expires_in,
    }


async def setup_integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payload: dict[str, Any] | None = None,
    token: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Add a config entry with a valid token, mock the API and set it up."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3f9a1c0b7d2e4a55",
        data={
            "auth_implementation": DOMAIN,
            "token": token if token is not None else token_data(),
        },
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, json=payload if payload is not None else account_payload())
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def sensor_state(hass: HomeAssistant, device_id: str, key: str) -> State | None:
    """State of a sensor by unique ID; entity IDs depend on the Home Assistant version."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{device_id}_{key}"
    )
    return hass.states.get(entity_id) if entity_id else None
