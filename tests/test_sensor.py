"""Tests for the sensor platform."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.icon import async_get_icons
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.clairsense import async_unload_entry
from custom_components.clairsense.const import API_URL, DOMAIN, SCAN_INTERVAL
from custom_components.clairsense.sensor import SENSORS, ClairsenseSensor

from .conftest import account_payload, sensor_state, setup_integration

ALL_READINGS = {
    "temperature": 22.4,
    "humidity": 41.0,
    "co2": 612,
    "pm25": 4.2,
    "pressure": 1013.2,
    "iaq": 52,
    "voc": 1.37,
    "infection_risk": 12,
}


def _device(device_id: str, name: str, readings: dict, online: bool = True) -> dict:
    return {
        "id": device_id,
        "name": name,
        "room": None,
        "firmware": "1.0.3",
        "online": online,
        "last_seen": "2026-11-11T09:30:00Z" if online else None,
        "readings": readings if online else {},
    }


async def _poll(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, payload=None, **kw) -> None:
    """Change what the API answers and let one scheduled poll run."""
    aioclient_mock.clear_requests()
    if kw:
        aioclient_mock.get(API_URL, **kw)
    else:
        aioclient_mock.get(API_URL, json=payload)
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()


async def test_sensors_created_with_classes_and_units(
    hass: HomeAssistant, aioclient_mock, device_registry: dr.DeviceRegistry
) -> None:
    entry = await setup_integration(
        hass, aioclient_mock, account_payload(readings=ALL_READINGS)
    )
    state = sensor_state(hass, "CS-A", "co2")
    assert state.state == "612"
    assert state.attributes["unit_of_measurement"] == "ppm"
    assert state.attributes["device_class"] == "carbon_dioxide"
    assert state.attributes["state_class"] == "measurement"
    voc = sensor_state(hass, "CS-A", "voc")
    assert voc.attributes["device_class"] == "volatile_organic_compounds_parts"
    assert voc.attributes["unit_of_measurement"] == "ppm"
    risk = sensor_state(hass, "CS-A", "infection_risk")
    assert risk.attributes["unit_of_measurement"] == "%"
    assert "device_class" not in risk.attributes
    iaq = sensor_state(hass, "CS-A", "iaq")
    assert iaq.attributes["device_class"] == "aqi"
    assert "unit_of_measurement" not in iaq.attributes
    assert len(hass.states.async_all("sensor")) == 8

    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert (DOMAIN, "CS-A") in device.identifiers
    assert (device.manufacturer, device.sw_version, device.suggested_area) == (
        "Clairsense",
        "1.0.3",
        "Salon",
    )


async def test_only_reported_readings_get_sensors(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(hass, aioclient_mock)
    assert len(hass.states.async_all("sensor")) == 2
    assert sensor_state(hass, "CS-A", "co2") is not None
    assert sensor_state(hass, "CS-A", "temperature") is not None
    assert sensor_state(hass, "CS-A", "pm25") is None


async def test_offline_device_sensors_are_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(hass, aioclient_mock)
    assert sensor_state(hass, "CS-A", "co2").state == "612"
    await _poll(hass, aioclient_mock, account_payload(online=False))
    assert sensor_state(hass, "CS-A", "co2").state == "unavailable"
    assert sensor_state(hass, "CS-A", "temperature").state == "unavailable"


async def test_missing_reading_is_unavailable_then_returns(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(hass, aioclient_mock)
    await _poll(hass, aioclient_mock, account_payload(readings={"temperature": 23.0}))
    assert sensor_state(hass, "CS-A", "co2").state == "unavailable"
    assert sensor_state(hass, "CS-A", "temperature").state == "23.0"
    await _poll(
        hass, aioclient_mock, account_payload(readings={"temperature": 23.5, "co2": 640})
    )
    assert sensor_state(hass, "CS-A", "co2").state == "640"
    assert sensor_state(hass, "CS-A", "temperature").state == "23.5"
    assert len(hass.states.async_all("sensor")) == 2


async def test_failed_update_makes_sensors_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(hass, aioclient_mock)
    await _poll(hass, aioclient_mock, status=503)
    assert sensor_state(hass, "CS-A", "co2").state == "unavailable"
    assert sensor_state(hass, "CS-A", "temperature").state == "unavailable"
    await _poll(hass, aioclient_mock, account_payload())
    assert sensor_state(hass, "CS-A", "co2").state == "612"


async def test_new_device_and_new_reading_appear(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(hass, aioclient_mock)
    assert len(hass.states.async_all("sensor")) == 2
    payload = account_payload(
        devices=[
            _device("CS-A", "Living room", {"temperature": 22.4, "co2": 612, "pm25": 4.0}),
            _device("CS-B", "Hall", {"humidity": 40}),
        ]
    )
    await _poll(hass, aioclient_mock, payload)
    assert sensor_state(hass, "CS-A", "pm25").state == "4.0"
    assert sensor_state(hass, "CS-B", "humidity").state == "40"
    assert len(hass.states.async_all("sensor")) == 4


async def test_device_first_seen_offline_gets_sensors_when_it_reports(
    hass: HomeAssistant, aioclient_mock
) -> None:
    await setup_integration(
        hass,
        aioclient_mock,
        account_payload(devices=[_device("CS-A", "Living room", {}, online=False)]),
    )
    assert hass.states.async_all("sensor") == []
    await _poll(hass, aioclient_mock, account_payload())
    assert sensor_state(hass, "CS-A", "co2").state == "612"
    assert len(hass.states.async_all("sensor")) == 2


async def test_device_gone_removes_sensors_and_returns_with_them(
    hass: HomeAssistant, aioclient_mock, entity_registry
) -> None:
    both = account_payload(
        devices=[
            _device("CS-A", "Living room", {"co2": 612}),
            _device("CS-B", "Hall", {"co2": 500}),
        ]
    )
    await setup_integration(hass, aioclient_mock, both)
    hall = entity_registry.async_get_entity_id("sensor", DOMAIN, "CS-B_co2")
    assert hass.states.get(hall).state == "500"

    await _poll(
        hass, aioclient_mock, account_payload(devices=[_device("CS-A", "Living room", {"co2": 612})])
    )
    assert hass.states.get(hall) is None
    assert entity_registry.async_get(hall) is None
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, "CS-B_co2") is None
    assert sensor_state(hass, "CS-A", "co2").state == "612"

    # A second poll without it: the device stays gone.
    await _poll(
        hass, aioclient_mock, account_payload(devices=[_device("CS-A", "Living room", {"co2": 612})])
    )
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, "CS-B_co2") is None
    assert len(hass.states.async_all("sensor")) == 1

    await _poll(hass, aioclient_mock, both)
    assert sensor_state(hass, "CS-B", "co2").state == "500"


async def test_no_safety_device_classes() -> None:
    classes = {d.device_class for d in SENSORS}
    assert not classes & {SensorDeviceClass.GAS, SensorDeviceClass.CO}
    assert not {c.value for c in classes if c} & {
        "gas",
        "carbon_monoxide",
        "smoke",
        "safety",
    }
    assert len(SENSORS) == 8
    package = Path(__file__).parent.parent / "custom_components" / "clairsense"
    modules = {p.stem for p in package.glob("*.py")}
    assert not modules & {"binary_sensor", "switch", "button", "number", "select", "light", "services"}


async def test_turkish_names(hass: HomeAssistant, aioclient_mock) -> None:
    hass.config.language = "tr"
    await setup_integration(hass, aioclient_mock)
    friendly = [
        s.attributes["friendly_name"] for s in hass.states.async_all("sensor")
    ]
    assert any(name.endswith("Karbondioksit") for name in friendly)
    assert any(name.endswith("Sıcaklık") for name in friendly)


async def test_sensor_device_info_only_links_to_the_device(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Adding a sensor must not re-apply the room, name or firmware."""
    entry = await setup_integration(hass, aioclient_mock)
    sensor = ClairsenseSensor(entry.runtime_data, "CS-A", SENSORS[0])
    assert sensor.device_info == {"identifiers": {(DOMAIN, "CS-A")}}


async def test_listener_after_platform_unload_adds_nothing(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A poll landing between the platform unload and the end of the entry unload."""
    entry = await setup_integration(hass, aioclient_mock)
    coordinator = entry.runtime_data

    async def _unload_then_poll(hass: HomeAssistant, entry) -> bool:
        unloaded = await async_unload_entry(hass, entry)
        coordinator.async_update_listeners()
        return unloaded

    with (
        patch("custom_components.clairsense.async_unload_entry", _unload_then_poll),
        patch("custom_components.clairsense.sensor.ClairsenseSensor") as sensor_class,
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    sensor_class.assert_not_called()


def test_infection_risk_icon() -> None:
    icons = Path(__file__).parent.parent / "custom_components" / "clairsense" / "icons.json"
    assert json.loads(icons.read_text()) == {
        "entity": {"sensor": {"infection_risk": {"default": "mdi:virus-outline"}}}
    }


async def test_home_assistant_loads_the_icon(hass: HomeAssistant) -> None:
    icons = await async_get_icons(hass, "entity", [DOMAIN])
    assert icons[DOMAIN]["sensor"]["infection_risk"]["default"] == "mdi:virus-outline"


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def test_dark_logo_matches_the_logo() -> None:
    brand = Path(__file__).parent.parent / "custom_components" / "clairsense" / "brand"
    assert _png_size(brand / "dark_logo.png") == _png_size(brand / "logo.png")
