"""Kiosk upsell suggestions, the overhead menu board screen, and remote screen commands."""

from typing import Any

import pytest

from kiosk.realtime.hub import hub
from tests.conftest import Api


async def test_suggestions_and_upsell_report(api: Api) -> None:
    c = api.client
    burger = api.items["Chicken Burger"]
    assert burger["suggest_ids"] == [api.items["French Fries"]["id"], api.items["Lime Juice"]["id"]]

    body = {k: burger[k] for k in ("category_id", "name", "price", "station")}
    r = await c.put(
        api.av(f"/menu/items/{burger['id']}"), headers=api.admin, json={**body, "suggest_ids": [burger["id"]]}
    )
    assert r.json()["error"]["code"] == "bad_suggestion", "an item cannot suggest itself"
    r = await c.put(
        api.av(f"/menu/items/{burger['id']}"), headers=api.admin, json={**body, "suggest_ids": ["nope"]}
    )
    assert r.json()["error"]["code"] == "bad_suggestion"

    kiosk = await api.device("Kiosk 1", "kiosk")
    cart = {"items": [api.line("Chicken Burger"), {**api.line("French Fries"), "source": "upsell"}]}
    order = (await c.post("/v1/orders", headers=kiosk, json=cart)).json()
    assert [i["source"] for i in order["items"]] == [None, "upsell"]
    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    ops = (await c.get(api.av("/reports/operations"), headers=api.admin)).json()
    assert ops["upsell"] == {"items": 1, "revenue": api.items["French Fries"]["price"]}


async def test_menu_board_screen(api: Api) -> None:
    c = api.client
    board = await api.device("Board 1", "board")
    me = (await c.get("/v1/devices/me", headers=board)).json()
    assert me["device"]["type"] == "board"
    assert me["venue"]["board_page_seconds"] == 12 and me["venue"]["attract_images"] == []
    menu = (await c.get("/v1/menu", headers=board)).json()
    assert menu["categories"], "the board shows the live menu"
    order = await c.post("/v1/orders", headers=board, json={"items": [api.line("Lime Juice")]})
    assert order.status_code == 403, "a menu board cannot place orders"


async def test_remote_commands(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    await api.device("Kitchen", "kds")
    dev = next(
        d for d in (await c.get(api.av("/devices"), headers=api.admin)).json() if d["name"] == "Kitchen"
    )
    sent: list[tuple[str, dict[str, Any], list[str]]] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append((type_, data, topics))
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    r = await c.post(
        api.av(f"/devices/{dev['id']}/command"), headers=api.installer, json={"command": "reload"}
    )
    assert r.json() == {"sent": False, "device_id": dev["id"], "command": "reload"}, (
        "not connected in the test"
    )
    assert sent == [
        ("device.command", {"device_id": dev["id"], "command": "reload"}, [f"device:{dev['id']}"])
    ]
    bad = await c.post(
        api.av(f"/devices/{dev['id']}/command"), headers=api.installer, json={"command": "wipe"}
    )
    assert bad.status_code == 422
