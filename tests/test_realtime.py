from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kiosk.config import settings
from kiosk.infra.db import create_all, session_factory
from kiosk.main import create_app
from kiosk.seed import seed


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path}/ws.db")
    monkeypatch.setattr(settings, "print_dir", str(tmp_path / "prints"))

    async def setup() -> dict[str, Any]:
        await create_all()
        async with session_factory()() as s:
            info = await seed(s)
            await s.commit()
        return info

    with TestClient(create_app()) as c:
        assert c.portal is not None
        c.info = c.portal.call(setup)  # type: ignore[attr-defined]
        yield c


def _pair(c: TestClient, admin: dict[str, str], venue: str, type_: str, **extra: str) -> str:
    r = c.post(
        f"/v1/admin/venues/{venue}/devices", headers=admin, json={"type": type_, "name": type_, **extra}
    )
    return c.post("/v1/devices/pair", json={"code": r.json()["pairing_code"]}).json()["device_token"]


def test_kds_gets_events_and_can_replay(client: TestClient) -> None:
    info = client.info  # type: ignore[attr-defined]
    venue = info["venue_id"]
    tok = client.post(
        "/v1/admin/auth/login", json={"email": info["admin_email"], "password": info["admin_password"]}
    ).json()
    admin = {"Authorization": f"Bearer {tok['access_token']}"}
    items = client.get(f"/v1/admin/venues/{venue}/menu/items", headers=admin).json()
    juice = next(i for i in items if i["name"]["en"] == "Lime Juice")
    client.patch(f"/v1/admin/venues/{venue}", headers=admin, json={"settings": {"release_rule": "B"}})

    plat = client.post(
        "/v1/platform/auth/login", json={"email": "platform@kiosk.lk", "password": "platform12345"}
    ).json()
    installer = {"Authorization": f"Bearer {plat['access_token']}"}
    kds = _pair(client, installer, venue, "kds")
    kiosk = _pair(client, installer, venue, "kiosk")

    with client.websocket_connect(f"/v1/ws?token={kds}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        client.post(
            "/v1/orders",
            headers={"X-Device-Token": kiosk},
            json={"items": [{"menu_item_id": juice["id"], "quantity": 1}]},
        )
        created = ws.receive_json()
        released = ws.receive_json()
        assert (created["type"], released["type"]) == ("order.created", "order.released")
        assert released["data"]["order"]["status"] == "in_kitchen"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"

    # Reconnect after missing events: replay from the last seq we saw
    client.post(
        "/v1/orders",
        headers={"X-Device-Token": kiosk},
        json={"items": [{"menu_item_id": juice["id"], "quantity": 2}]},
    )
    url = f"/v1/ws?token={kds}&since={released['seq']}&epoch={hello['epoch']}"
    with client.websocket_connect(url) as ws:
        assert ws.receive_json()["type"] == "hello"
        missed = ws.receive_json()
        assert missed["type"] == "order.created" and missed["seq"] == released["seq"] + 1

    # A different epoch (server restarted) means resync from REST
    with client.websocket_connect(f"/v1/ws?token={kds}&since=1&epoch=old") as ws:
        ws.receive_json()
        assert ws.receive_json()["type"] == "resync"


def test_ws_rejects_bad_token(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/v1/ws?token=bad") as ws:
        ws.receive_json()
