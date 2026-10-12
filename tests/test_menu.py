"""Menu manager: combos, per-screen categories, sold-out alerts, photo upload."""

from typing import Any

import pytest

from kiosk.realtime.hub import hub
from tests.conftest import Api


def combo_line(api: Api, drink: str = "Lime Juice", qty: int = 1) -> dict[str, Any]:
    meal = api.items["Burger Meal"]
    choices = [api.items["Chicken Burger"]["id"], api.items["French Fries"]["id"], api.items[drink]["id"]]
    return {"menu_item_id": meal["id"], "quantity": qty, "combo_choices": choices}


async def test_combo_order_splits_parts_to_their_stations(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    grill = await api.device("Grill", "kds", station="grill")
    bar = await api.device("Bar", "kds", station="bar")
    meal = api.items["Burger Meal"]
    assert len(meal["combo_slots"]) == 3

    q = (
        await c.post("/v1/orders/quote", headers=kiosk, json={"items": [combo_line(api, "Iced Milo", 2)]})
    ).json()
    assert q["subtotal"] == 2 * (130_000 + 5_000), "combo price + large-drink upcharge"

    order = (
        await c.post("/v1/orders", headers=kiosk, json={"items": [combo_line(api, "Iced Milo", 2)]})
    ).json()
    lines = order["items"]
    assert [(i["name"]["en"], i["line_total"], i["parent_position"]) for i in lines] == [
        ("Burger Meal", 270_000, None),
        ("Chicken Burger", 0, 0),
        ("French Fries", 0, 0),
        ("Iced Milo", 0, 0),
    ]
    assert lines[0]["station"] == "none" and lines[0]["kds_status"] == "done"
    assert {i["station"] for i in lines[1:]} == {"grill", "fryer", "bar"}
    assert all(i["quantity"] == 2 for i in lines)
    assert set(lines[0]["allergens"]) >= {"gluten", "milk"}

    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    grill_items = (await c.get("/v1/kds/tickets", headers=grill)).json()["tickets"][0]["items"]
    assert [i["name"]["en"] for i in grill_items] == ["Chicken Burger"], (
        "the combo line is not a kitchen item"
    )
    assert [
        i["name"]["en"] for i in (await c.get("/v1/kds/tickets", headers=bar)).json()["tickets"][0]["items"]
    ] == ["Iced Milo"]
    fryer = await api.device("Fryer", "kds", station="fryer")
    for kds in (grill, bar, fryer):
        await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    assert (await c.get(f"/v1/orders/{order['id']}", headers=kiosk)).json()["status"] == "ready"


async def test_combo_choices_are_checked(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    meal = api.items["Burger Meal"]["id"]
    bad = {"menu_item_id": meal, "quantity": 1, "combo_choices": [api.items["Chicken Burger"]["id"]]}
    assert (await c.post("/v1/orders/quote", headers=kiosk, json={"items": [bad]})).json()["error"][
        "code"
    ] == "bad_combo"
    wrong = combo_line(api)
    wrong["combo_choices"][2] = api.items["Chicken Kottu"]["id"]
    assert (await c.post("/v1/orders/quote", headers=kiosk, json={"items": [wrong]})).json()["error"][
        "code"
    ] == "bad_combo"
    not_combo = {**api.line("Lime Juice"), "combo_choices": [api.items["Iced Milo"]["id"]]}
    r = await c.post("/v1/orders/quote", headers=kiosk, json={"items": [not_combo]})
    assert r.json()["error"]["code"] == "not_a_combo"
    # A sold-out part makes the combo unavailable with that choice.
    kds = await api.device("Kitchen", "kds")
    await c.put(
        f"/v1/menu/items/{api.items['French Fries']['id']}/availability",
        headers=kds,
        json={"is_available": False},
    )
    r = await c.post("/v1/orders/quote", headers=kiosk, json={"items": [combo_line(api)]})
    assert r.json()["error"]["code"] == "item_unavailable"


async def test_admin_combo_rules(api: Api) -> None:
    c = api.client
    meal = api.items["Burger Meal"]
    body = {**{k: meal[k] for k in ("category_id", "name", "price", "station")}}
    body["combo_slots"] = [{"name": {"en": "Meal"}, "item_ids": [meal["id"]]}]
    r = await c.put(api.av(f"/menu/items/{meal['id']}"), headers=api.admin, json=body)
    assert r.json()["error"]["code"] == "bad_combo", "a combo cannot contain itself"
    body["combo_slots"] = [{"name": {"en": "x"}, "item_ids": ["nope"]}]
    r = await c.post(api.av("/menu/items"), headers=api.admin, json={**body, "name": {"en": "Bad"}})
    assert r.json()["error"]["code"] == "bad_combo"
    body["combo_slots"] = [{"name": {"en": "Main"}, "item_ids": [meal["id"]]}]
    r = await c.post(api.av("/menu/items"), headers=api.admin, json={**body, "name": {"en": "Double"}})
    assert r.json()["error"]["code"] == "bad_combo", "no combo inside a combo"


async def test_screen_shows_only_its_categories(api: Api) -> None:
    c = api.client
    await api.device("Drinks kiosk", "kiosk")
    kiosk = {"X-Device-Token": api.devices["Drinks kiosk"]}
    cats = (await c.get(api.av("/menu/categories"), headers=api.admin)).json()
    drinks = next(x for x in cats if x["name"]["en"] == "Drinks")
    devices = (await c.get(api.av("/devices"), headers=api.admin)).json()
    dev = next(d for d in devices if d["name"] == "Drinks kiosk")
    r = await c.patch(
        api.av(f"/devices/{dev['id']}"), headers=api.installer, json={"menu_categories": [drinks["id"]]}
    )
    assert r.json()["menu_categories"] == [drinks["id"]]
    menu = (await c.get("/v1/menu", headers=kiosk)).json()
    assert [x["name"]["en"] for x in menu["categories"]] == ["Drinks"]
    await c.patch(api.av(f"/devices/{dev['id']}"), headers=api.installer, json={"menu_categories": []})
    assert len((await c.get("/v1/menu", headers=kiosk)).json()["categories"]) >= 3
    r = await c.patch(
        api.av(f"/devices/{dev['id']}"), headers=api.installer, json={"menu_categories": ["nope"]}
    )
    assert r.json()["error"]["code"] == "bad_category"


async def test_sold_out_alerts_staff_about_placed_orders(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    table = await api.device("Table 1", "table", table_ref="T1")
    kds = await api.device("Kitchen", "kds")
    order = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Chicken Burger")]})).json()
    sent: list[tuple[str, dict[str, Any]]] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append((type_, data))
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    await c.put(
        f"/v1/menu/items/{api.items['Chicken Burger']['id']}/availability",
        headers=kds,
        json={"is_available": False},
    )
    alerts = [d for t, d in sent if t == "menu.sold_out_alert"]
    assert alerts and alerts[0]["orders"] == [
        {"order_id": order["id"], "token": order["token"], "table_ref": "T1"}
    ]
    sent.clear()
    await c.put(
        f"/v1/menu/items/{api.items['Lime Juice']['id']}/availability",
        headers=kds,
        json={"is_available": False},
    )
    assert not [d for t, d in sent if t == "menu.sold_out_alert"], "no alert when no order needs the item"


async def test_photo_upload(api: Api) -> None:
    c = api.client
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = await c.post(api.av("/media"), headers={**api.admin, "Content-Type": "image/png"}, content=png)
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith(f"/media/{api.venue_id}/") and url.endswith(".png")
    assert (await c.get(url)).content == png
    r = await c.post(
        api.av("/media"), headers={**api.admin, "Content-Type": "image/png"}, content=b"GIF89a...."
    )
    assert r.json()["error"]["code"] == "bad_image"
    r = await c.post(
        api.av("/media"), headers={**api.admin, "Content-Type": "text/html"}, content=b"<script>"
    )
    assert r.json()["error"]["code"] == "bad_image"
    assert (
        await c.post(api.av("/media"), headers={"Content-Type": "image/png"}, content=png)
    ).status_code == 401
