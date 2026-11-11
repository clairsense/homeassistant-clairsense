"""Client for the Clairsense smart home API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import Any

import aiohttp

from .const import API_URL

REQUEST_TIMEOUT = 10

KNOWN_READINGS = (
    "temperature",
    "humidity",
    "co2",
    "pm25",
    "pressure",
    "iaq",
    "voc",
    "infection_risk",
)


class ClairsenseAuthError(Exception):
    """The access token was rejected."""


class ClairsenseApiError(Exception):
    """The API could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class Device:
    """One Clairsense monitor."""

    id: str
    name: str
    room: str | None
    firmware: str | None
    online: bool
    last_seen: datetime | None
    readings: dict[str, float]


@dataclass(frozen=True)
class Account:
    """A Clairsense account and its monitors."""

    account_id: str
    devices: dict[str, Device]


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_last_seen(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_readings(raw: Any) -> dict[str, float]:
    """Keep known readings that are real numbers, with their original type."""
    if not isinstance(raw, dict):
        return {}
    readings: dict[str, float] = {}
    for key in KNOWN_READINGS:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        readings[key] = value
    return readings


def _parse_device(raw: Any) -> Device:
    if not isinstance(raw, dict):
        raise ClairsenseApiError("Device entry is not an object")
    device_id = raw.get("id")
    if not isinstance(device_id, str) or not device_id:
        raise ClairsenseApiError("Device entry has no id")
    online = raw.get("online") is True
    return Device(
        id=device_id,
        name=_optional_str(raw.get("name")) or device_id,
        room=_optional_str(raw.get("room")),
        firmware=_optional_str(raw.get("firmware")),
        online=online,
        last_seen=_parse_last_seen(raw.get("last_seen")) if online else None,
        readings=_parse_readings(raw.get("readings")) if online else {},
    )


def _parse_account(body: Any) -> Account:
    if not isinstance(body, dict):
        raise ClairsenseApiError("Response is not an object")
    account_id = body.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        raise ClairsenseApiError("Response has no account_id")
    raw_devices = body.get("devices")
    if not isinstance(raw_devices, list):
        raise ClairsenseApiError("Response devices is not a list")
    devices = [_parse_device(raw) for raw in raw_devices]
    return Account(account_id, {device.id: device for device in devices})


async def async_get_account(
    session: aiohttp.ClientSession, access_token: str
) -> Account:
    """Fetch the account and its devices."""
    try:
        async with (
            asyncio.timeout(REQUEST_TIMEOUT),
            session.get(
                API_URL, headers={"Authorization": f"Bearer {access_token}"}
            ) as response,
        ):
            if response.status == 401:
                raise ClairsenseAuthError("Access token rejected")
            if response.status != 200:
                raise ClairsenseApiError(f"Unexpected status {response.status}")
            body = await response.json()
    except TimeoutError as err:
        raise ClairsenseApiError("Request timed out") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise ClairsenseApiError(f"Request failed: {err}") from err
    return _parse_account(body)
