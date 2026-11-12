"""Tests for entry setup, the coordinator and removal."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import time
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.clairsense.const import (
    API_URL,
    DOMAIN,
    MANUFACTURER,
    REVOKE_URL,
    SCAN_INTERVAL,
    TOKEN_URL,
)

from .conftest import account_payload, setup_integration, token_data


def _device(device_id: str, name: str = "Device") -> dict:
    return account_payload(
        devices=[
            {
                "id": device_id,
                "name": name,
                "room": None,
                "firmware": "1.0.3",
                "online": True,
                "last_seen": "2026-11-11T09:30:00Z",
                "readings": {"co2": 600},
            }
        ]
    )["devices"][0]


def _registered(device_registry: dr.DeviceRegistry, entry) -> set[str]:
    return {
        ident[1]
        for dev in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        for ident in dev.identifiers
        if ident[0] == DOMAIN
    }


async def test_setup_and_unload(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_first_refresh_failure_retries_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3f9a1c0b7d2e4a55",
        data={"auth_implementation": DOMAIN, "token": token_data()},
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, status=503)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_401_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, status=401)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_refresh_rejected_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
    entry = await setup_integration(
        hass, aioclient_mock, token=token_data(expires_in=-100)
    )
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_refresh_server_error_is_not_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(TOKEN_URL, status=503)
    entry = await setup_integration(
        hass, aioclient_mock, token=token_data(expires_in=-100)
    )
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress() == []


async def test_expired_token_is_refreshed_and_stored(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        TOKEN_URL,
        json={
            "access_token": "access-2",
            "refresh_token": "refresh-2",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    entry = await setup_integration(
        hass, aioclient_mock, token=token_data(expires_in=-100)
    )
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["token"]["access_token"] == "access-2"
    assert entry.data["token"]["refresh_token"] == "refresh-2"
    assert entry.data["token"]["expires_at"] > time.time()
    api_calls = [c for c in aioclient_mock.mock_calls if str(c[1]) == API_URL]
    assert api_calls[-1][3]["Authorization"] == "Bearer access-2"


async def test_failed_update_removes_nothing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    assert _registered(device_registry, entry) == {"CS-A"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, status=503)
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success is False
    assert _registered(device_registry, entry) == {"CS-A"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, exc=TimeoutError)
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success is False
    assert _registered(device_registry, entry) == {"CS-A"}


async def test_device_gone_from_account_is_removed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    entry = await setup_integration(
        hass,
        aioclient_mock,
        account_payload(devices=[_device("CS-A"), _device("CS-B")]),
    )
    assert _registered(device_registry, entry) == {"CS-A", "CS-B"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=account_payload(devices=[_device("CS-B")]))
    await entry.runtime_data.async_refresh()
    assert _registered(device_registry, entry) == {"CS-B"}


async def test_new_device_is_registered_on_later_poll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    assert _registered(device_registry, entry) == {"CS-A"}
    # The coordinator only schedules polls while something listens (sensors, from Task 4).
    entry.runtime_data.async_add_listener(lambda: None)

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        API_URL, json=account_payload(devices=[_device("CS-A"), _device("CS-C", "Hall")])
    )
    async_fire_time_changed(hass, dt_now_plus(SCAN_INTERVAL + timedelta(seconds=5)))
    await hass.async_block_till_done()
    assert _registered(device_registry, entry) == {"CS-A", "CS-C"}
    device = next(
        d
        for d in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if (DOMAIN, "CS-C") in d.identifiers
    )
    assert device.name == "Hall"
    assert device.manufacturer == MANUFACTURER
    assert device.sw_version == "1.0.3"


def _device_entry(
    device_registry: dr.DeviceRegistry, entry, device_id: str = "CS-A"
) -> dr.DeviceEntry:
    return next(
        device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if (DOMAIN, device_id) in device.identifiers
    )


async def _refresh(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entry, payload) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=payload)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_cleared_area_stays_cleared(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    device = _device_entry(device_registry, entry)
    assert device.area_id == "salon"

    device_registry.async_update_device(device.id, area_id=None)
    await _refresh(hass, aioclient_mock, entry, account_payload())
    assert _device_entry(device_registry, entry).area_id is None

    # Setting the sensors up again does not bring the area back either.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _device_entry(device_registry, entry).area_id is None


async def test_deleted_area_is_not_recreated(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    area_registry.async_delete(_device_entry(device_registry, entry).area_id)
    assert _device_entry(device_registry, entry).area_id is None

    await _refresh(hass, aioclient_mock, entry, account_payload())
    assert _device_entry(device_registry, entry).area_id is None
    assert area_registry.async_get_area_by_name("Salon") is None


async def test_rename_and_new_firmware_update_the_registry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    device_registry.async_update_device(
        _device_entry(device_registry, entry).id, name_by_user="My monitor"
    )
    payload = account_payload()
    payload["devices"][0].update(name="Kitchen", firmware="1.0.4")
    await _refresh(hass, aioclient_mock, entry, payload)

    device = _device_entry(device_registry, entry)
    assert (device.name, device.sw_version) == ("Kitchen", "1.0.4")
    assert device.name_by_user == "My monitor"
    assert device.manufacturer == MANUFACTURER


async def test_model_is_shown_on_a_new_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    payload = account_payload()
    payload["devices"][0]["model"] = "CLS-V1M1"
    entry = await setup_integration(hass, aioclient_mock, payload)
    device = _device_entry(device_registry, entry)
    assert (device.manufacturer, device.model) == (MANUFACTURER, "CLS-V1M1")


async def test_model_reaches_a_device_registered_without_one(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Devices linked before the bridge sent a model get it on the next poll."""
    entry = await setup_integration(hass, aioclient_mock)
    before = _device_entry(device_registry, entry)
    assert before.model is None
    device_registry.async_update_device(before.id, name_by_user="My monitor", area_id=None)

    payload = account_payload()
    payload["devices"][0]["model"] = "CLS-V1M1"
    await _refresh(hass, aioclient_mock, entry, payload)
    device = _device_entry(device_registry, entry)
    assert (device.model, device.name, device.sw_version) == ("CLS-V1M1", "Living room", "1.0.3")
    # What the user set stays theirs.
    assert (device.name_by_user, device.area_id) == ("My monitor", None)

    payload["devices"][0]["model"] = "CLS-V2M1"
    await _refresh(hass, aioclient_mock, entry, payload)
    assert _device_entry(device_registry, entry).model == "CLS-V2M1"


async def test_maker_is_the_brand(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Home Assistant heads a device with maker and model: "Clairsense CLS-V1M1"."""
    payload = account_payload()
    payload["devices"][0]["model"] = "CLS-V1M1"
    entry = await setup_integration(hass, aioclient_mock, payload)
    device = _device_entry(device_registry, entry)
    assert (device.manufacturer, device.model) == ("Clairsense", "CLS-V1M1")


async def test_maker_reaches_a_device_registered_under_the_old_one(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Devices linked while the maker was "ARTEQ" follow on the next poll."""
    entry = await setup_integration(hass, aioclient_mock)
    linked = _device_entry(device_registry, entry)
    device_registry.async_update_device(
        linked.id, manufacturer="ARTEQ", name_by_user="My monitor", area_id=None
    )
    assert _device_entry(device_registry, entry).manufacturer == "ARTEQ"

    await _refresh(hass, aioclient_mock, entry, account_payload())
    device = _device_entry(device_registry, entry)
    assert device.manufacturer == "Clairsense"
    assert (device.name, device.sw_version) == ("Living room", "1.0.3")
    assert (device.name_by_user, device.area_id) == ("My monitor", None)


async def test_unchanged_device_is_not_rewritten(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
) -> None:
    payload = account_payload()
    payload["devices"][0]["model"] = "CLS-V1M1"
    entry = await setup_integration(hass, aioclient_mock, payload)
    with patch.object(
        device_registry, "async_update_device", wraps=device_registry.async_update_device
    ) as update:
        await _refresh(hass, aioclient_mock, entry, payload)
    assert update.call_count == 0


async def test_remove_entry_revokes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    aioclient_mock.post(REVOKE_URL, status=200)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    calls = [c for c in aioclient_mock.mock_calls if str(c[1]) == REVOKE_URL]
    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][2] == {"token": "refresh-1", "client_id": "home-assistant"}


async def test_remove_entry_survives_revoke_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await setup_integration(hass, aioclient_mock)
    aioclient_mock.post(REVOKE_URL, status=500)
    assert await hass.config_entries.async_remove(entry.entry_id)

    entry2 = await setup_integration(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(REVOKE_URL, exc=TimeoutError)
    assert await hass.config_entries.async_remove(entry2.entry_id)
    assert hass.config_entries.async_get_entry(entry2.entry_id) is None


async def test_remove_entry_does_not_wait_for_a_hanging_revoke(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await setup_integration(hass, aioclient_mock)

    async def _hang(method, url, data):
        await asyncio.Event().wait()

    aioclient_mock.post(REVOKE_URL, side_effect=_hang)
    with patch("custom_components.clairsense.api.REVOKE_TIMEOUT", 0.01):
        async with asyncio.timeout(2):
            assert await hass.config_entries.async_remove(entry.entry_id)
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    calls = [c for c in aioclient_mock.mock_calls if str(c[1]) == REVOKE_URL]
    assert len(calls) == 1


def dt_now_plus(delta):
    from homeassistant.util import dt as dt_util

    return dt_util.utcnow() + delta
