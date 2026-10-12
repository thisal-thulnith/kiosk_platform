"""Self-order kiosks and status boards are "Coming soon" until switched on (COMING_SOON setting)."""

import pytest

from kiosk.config import settings
from tests.conftest import Api


async def test_coming_soon_screens(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    monkeypatch.setattr(settings, "coming_soon", "kiosk,status")
    assert (await c.get("/v1/features")).json()["coming_soon"] == ["kiosk", "status"]
    r = await c.post(api.av("/devices"), headers=api.installer, json={"type": "kiosk", "name": "Kiosk 1"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "coming_soon"
    r = await c.post(api.av("/devices"), headers=api.installer, json={"type": "kds", "name": "Kitchen"})
    assert r.status_code == 201, "everything else works as before"
    monkeypatch.setattr(settings, "coming_soon", "")
    assert (await c.get("/v1/features")).json()["coming_soon"] == []
