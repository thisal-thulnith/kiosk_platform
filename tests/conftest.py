import os

os.environ.update(
    {
        "ENV": "test",
        "APP_MODE": "edge",
        "RUN_BACKGROUND_JOBS": "false",
        "PRINT_ASYNC": "false",
        "CLOUD_URL": "",
        "COMING_SOON": "",  # tests cover every screen, including the ones not offered yet
    }
)

from collections.abc import AsyncIterator  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from kiosk.config import settings  # noqa: E402
from kiosk.infra.db import create_all, get_engine, session_factory  # noqa: E402
from kiosk.infra.models import Base  # noqa: E402
from kiosk.main import create_app  # noqa: E402
from kiosk.seed import seed  # noqa: E402


@pytest.fixture
async def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    from kiosk.api import limits

    limits.reset()  # wrong-attempt counters are per process
    # Set TEST_POSTGRES_URL to run the API tests against Postgres instead of SQLite.
    pg = os.environ.get("TEST_POSTGRES_URL")
    monkeypatch.setattr(settings, "database_url", pg or f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setattr(settings, "print_dir", str(tmp_path / "prints"))
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "cloud_url", None)
    application = create_app()
    if pg:
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await create_all()
    yield application
    await get_engine().dispose()


@dataclass
class Api:
    """Test helper that plays admin, devices and staff against the real app."""

    client: httpx.AsyncClient
    venue_id: str
    admin_token: str = ""  # the restaurant's own admin (owner)
    installer_token: str = ""  # our installation team (platform login): screens, printers, payments
    devices: dict[str, str] = field(default_factory=dict)  # name -> device token
    staff_ids: dict[str, str] = field(default_factory=dict)  # name -> staff id
    items: dict[str, dict[str, Any]] = field(default_factory=dict)  # en name -> menu item

    @property
    def admin(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.admin_token}"}

    @property
    def installer(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.installer_token}"}

    def av(self, path: str = "") -> str:
        return f"/v1/admin/venues/{self.venue_id}{path}"

    async def device(self, name: str, type_: str, **extra: Any) -> dict[str, str]:
        r = await self.client.post(
            self.av("/devices"), headers=self.installer, json={"type": type_, "name": name, **extra}
        )
        assert r.status_code == 201, r.text
        p = await self.client.post("/v1/devices/pair", json={"code": r.json()["pairing_code"]})
        assert p.status_code == 200, p.text
        self.devices[name] = p.json()["device_token"]
        return {"X-Device-Token": self.devices[name]}

    async def login(self, device_headers: dict[str, str], staff: str, pin: str) -> dict[str, str]:
        r = await self.client.post(
            "/v1/staff/pin-login",
            headers=device_headers,
            json={"staff_id": self.staff_ids[staff], "pin": pin},
        )
        assert r.status_code == 200, r.text
        return {**device_headers, "Authorization": f"Bearer {r.json()['staff_token']}"}

    async def venue_settings(self, **values: Any) -> None:
        r = await self.client.patch(self.av(), headers=self.admin, json={"settings": values})
        assert r.status_code == 200, r.text

    def line(self, name: str, qty: int = 1, modifiers: list[str] | None = None) -> dict[str, Any]:
        item = self.items[name]
        mods = []
        for m in modifiers or []:
            for g in item["modifier_groups"]:
                mods += [x["id"] for x in g["modifiers"] if x["name"]["en"] == m]
        return {"menu_item_id": item["id"], "quantity": qty, "modifier_ids": mods}


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[Api]:
    async with session_factory()() as session:
        info = await seed(session)
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        a = Api(client, info["venue_id"])
        r = await client.post(
            "/v1/admin/auth/login", json={"email": info["admin_email"], "password": info["admin_password"]}
        )
        a.admin_token = r.json()["access_token"]
        r = await client.post(
            "/v1/platform/auth/login", json={"email": "platform@kiosk.lk", "password": "platform12345"}
        )
        a.installer_token = r.json()["access_token"]
        staff = (await client.get(a.av("/staff"), headers=a.admin)).json()
        a.staff_ids = {s["name"]: s["id"] for s in staff}
        items = (await client.get(a.av("/menu/items"), headers=a.admin)).json()
        a.items = {i["name"]["en"]: i for i in items}
        yield a
