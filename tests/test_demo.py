"""The public demo server (DEMO_MODE): /try opens every screen of the demo restaurant with one tap.
Off everywhere else."""

import pytest

from kiosk.config import settings
from tests.conftest import Api


async def test_demo_is_off_on_real_servers(api: Api) -> None:
    c = api.client
    assert (await c.get("/v1/demo")).status_code == 404
    assert (await c.post("/v1/demo/screen", json={"type": "table", "table_ref": "T1"})).status_code == 404
    assert (await c.get("/try")).status_code == 404


async def test_demo_opens_every_screen(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    monkeypatch.setattr(settings, "demo_mode", True)
    assert (await c.get("/", follow_redirects=False)).headers["location"] == "/try"
    info = (await c.get("/v1/demo")).json()
    assert info["venue"]["code"] == "demo" and info["style"] == "sit_down" and "T1" in info["tables"]
    assert {s["name"]: s["pin"] for s in info["staff"]}["Priya"] == "3333"

    # A table and the kitchen, signed in like a real screen: the table's order reaches the kitchen.
    table = (await c.post("/v1/demo/screen", json={"type": "table", "table_ref": "T1"})).json()
    kitchen = (await c.post("/v1/demo/screen", json={"type": "kds"})).json()
    assert table["device"]["table_ref"] == "T1" and table["device"]["venue_code"] == "DEMO"
    th = {"X-Device-Token": table["device_token"]}
    me = (await c.get("/v1/devices/me", headers=th)).json()
    assert me["venue"]["dine_in_mode"] == "tab" and me["venue"]["serve_mode"] == "waiter"
    order = await c.post("/v1/orders", headers=th, json={"items": [api.line("Chicken Burger")]})
    assert order.status_code == 201 and order.json()["status"] == "in_kitchen"
    tickets = (await c.get("/v1/kds/tickets", headers={"X-Device-Token": kitchen["device_token"]})).json()
    assert any(t["order_id"] == order.json()["id"] for t in tickets["tickets"])
    assert (await c.post("/v1/demo/screen", json={"type": "table", "table_ref": "X9"})).status_code == 400

    # Quick service: screens follow the switch.
    assert (await c.post("/v1/demo/style", json={"style": "quick"})).json() == {"style": "quick"}
    me = (await c.get("/v1/devices/me", headers=th)).json()
    assert me["venue"]["dine_in_mode"] == "pay_first" and me["venue"]["serve_mode"] == "self_pickup"
