"""Shared fixtures for the Clairsense tests."""

from __future__ import annotations

from typing import Any

import pytest


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
