"""Inventory (R-INV): sales take stock off, voids give it back, auto sold-out and back on,
low-stock alerts, waste from the kitchen, and AI level 4 deals within the owner's cap."""

from datetime import timedelta
from typing import Any

import pytest

from kiosk.infra.models import utcnow
from kiosk.realtime.hub import hub
from tests.conftest import Api
from tests.test_tenancy import platform_headers


async def till(api: Api, who: str = "Nimal", pin: str = "1111") -> dict[str, str]:
    t = await api.login(await api.device(f"Till {who}", "cashier"), who, pin)
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 1_000_000})
    return t


async def paid(api: Api, t: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    c = api.client
    o = (await c.post("/v1/orders", headers=t, json={"items": items})).json()
    assert "id" in o, o
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=t, json={"tendered": o["total"]})
    assert r.status_code == 201, r.text
    return r.json()["order"]


async def track(api: Api, name: str, **body: Any) -> dict[str, Any]:
    r = await api.client.put(api.av(f"/stock/{api.items[name]['id']}"), headers=api.admin, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def menu_item(menu: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(i for c in menu["categories"] for i in c["items"] if i["id"] == item_id)


async def test_sales_void_sold_out_and_restock(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append((type_, data))
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    c = api.client
    lime = api.items["Lime Juice"]["id"]
    assert (await track(api, "Lime Juice", on_hand=3, low_at=1))["state"] == "ok"
    t = await till(api)

    await paid(api, t, [api.line("Lime Juice", 2), api.line("French Fries")])
    stock = (await c.get(api.av("/stock"), headers=api.admin)).json()
    assert stock["items"][0]["on_hand"] == 1 and stock["items"][0]["state"] == "low"
    assert any(t_ == "stock.low" and d["on_hand"] == 1 for t_, d in sent)

    r = await c.post("/v1/orders", headers=t, json={"items": [api.line("Lime Juice", 2)]})
    assert r.json()["error"]["code"] == "not_enough_stock" and "Only 1" in r.json()["error"]["message"]

    await paid(api, t, [api.line("Lime Juice")])
    kiosk = await api.device("Kiosk 1", "kiosk")
    assert menu_item((await c.get("/v1/menu", headers=kiosk)).json(), lime)["is_available"] is False
    assert any(t_ == "menu.item_availability" and d.get("by") == "stock" for t_, d in sent)
    r = await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})
    assert r.json()["error"]["code"] == "item_unavailable"

    # A delivery puts it back on every screen by itself.
    r = await c.post(
        api.av(f"/stock/{lime}/moves"), headers=api.admin, json={"kind": "delivery", "quantity": 5}
    )
    assert r.json()["on_hand"] == 5 and r.json()["is_available"] is True

    # Void before cooking: the portion goes back on the shelf.
    order = await paid(api, t, [api.line("Lime Juice")])
    manager = await till(api, "Kamala", "9999")
    r = await c.post(f"/v1/orders/{order['id']}/void", headers=manager, json={"reason": "guest left"})
    assert r.json()["status"] == "voided"
    stock = (await c.get(api.av("/stock"), headers=api.admin)).json()
    assert stock["items"][0]["on_hand"] == 5
    assert [m["reason"] for m in stock["moves"]][:3] == ["void_return", "sale", "delivery"]


async def test_kitchen_waste_counts_and_rules(api: Api) -> None:
    c = api.client
    fries = api.items["French Fries"]["id"]
    await track(api, "French Fries", on_hand=10, low_at=2)
    kds = await api.device("Fry station", "kds")
    r = await c.post(f"/v1/stock/{fries}/moves", headers=kds, json={"kind": "waste", "quantity": 3})
    assert r.json()["on_hand"] == 7
    r = await c.post(f"/v1/stock/{fries}/moves", headers=kds, json={"kind": "waste", "quantity": 30})
    assert r.json()["error"]["code"] == "bad_quantity"
    r = await c.post(f"/v1/stock/{fries}/moves", headers=kds, json={"kind": "count", "quantity": 4})
    assert r.json()["on_hand"] == 4
    low = (await c.get("/v1/stock", headers=kds)).json()
    assert low["items"][0]["state"] == "ok"
    overview = (await c.get(api.av("/stock"), headers=api.admin)).json()
    assert overview["waste_recent"] == {fries: 3}

    # A till needs a staff PIN to log stock.
    till_dev = await api.device("Till 9", "cashier")
    r = await c.post(f"/v1/stock/{fries}/moves", headers=till_dev, json={"kind": "delivery", "quantity": 1})
    assert r.status_code == 403

    # Untracked again: unlimited, and back on if stock had switched it off.
    await c.post(f"/v1/stock/{fries}/moves", headers=kds, json={"kind": "count", "quantity": 0})
    r = await c.delete(api.av(f"/stock/{fries}"), headers=api.admin)
    assert r.json()["tracked"] is False
    kiosk = await api.device("Kiosk 1", "kiosk")
    assert menu_item((await c.get("/v1/menu", headers=kiosk)).json(), fries)["is_available"] is True


async def test_inventory_needs_module(api: Api) -> None:
    plan = {"pack": "pack2", "tier": "starter", "create_slots": False}
    await api.client.put(
        f"/v1/platform/venues/{api.venue_id}/plan", headers=await platform_headers(api), json=plan
    )
    r = await api.client.get(api.av("/stock"), headers=api.admin)
    assert r.json()["error"]["code"] == "module_not_in_plan"
    r = await api.client.patch(api.av(), headers=api.admin, json={"settings": {"mode": "ai", "ai_level": 4}})
    assert r.json()["error"]["code"] == "bad_setting" and "R-INV" in r.json()["error"]["message"]


async def test_level_4_deals_need_owner_approval_and_stay_in_cap(api: Api) -> None:
    c = api.client
    burger = api.items["Chicken Burger"]
    price = burger["price"]
    r = await c.patch(api.av(), headers=api.admin, json={"settings": {"ai_price_cap_bp": 6000}})
    assert r.json()["error"]["code"] == "bad_setting", "at most 50% off"
    await api.venue_settings(mode="ai", ai_level=4)
    soon = (utcnow() + timedelta(minutes=45)).isoformat()
    await track(api, "Chicken Burger", on_hand=20, low_at=2, perishable_until=soon)
    await track(api, "Lime Juice", on_hand=3, low_at=2, perishable_until=soon)  # not plenty: no deal

    owner = (await c.get(api.av("/ai"), headers=api.admin)).json()
    [offer] = owner["offers"]
    assert offer["menu_item_id"] == burger["id"] and offer["status"] == "proposed"
    assert offer["discount_bp"] == 1000 and offer["offer_price"] == price - price // 10
    assert "use by" in offer["reason"]
    assert any(x["kind"] == "offer" for x in owner["log"])
    again = (await c.get(api.av("/ai"), headers=api.admin)).json()
    assert len(again["offers"]) == 1, "one deal per batch"

    kiosk = await api.device("Kiosk 1", "kiosk")
    quote = lambda: c.post("/v1/orders/quote", headers=kiosk, json={"items": [api.line("Chicken Burger")]})  # noqa: E731
    assert (await quote()).json()["subtotal"] == price, "nothing changes before the owner approves"

    r = await c.post(api.av(f"/ai/offers/{offer['id']}/approve"), headers=api.admin)
    assert r.json()["status"] == "active" and r.json()["decided_by"]
    shown = menu_item((await c.get("/v1/menu", headers=kiosk)).json(), burger["id"])
    assert shown["price"] == price and shown["offer"]["price"] == price - price // 10
    assert (await quote()).json()["subtotal"] == price - price // 10
    r = await c.post(api.av(f"/ai/offers/{offer['id']}/approve"), headers=api.admin)
    assert r.json()["error"]["code"] == "offer_decided"

    # Kill switch: Manual mode ends every deal at once.
    await api.venue_settings(mode="manual")
    assert (await quote()).json()["subtotal"] == price
    assert "offer" not in menu_item((await c.get("/v1/menu", headers=kiosk)).json(), burger["id"])

    # Owner can stop an active deal.
    await api.venue_settings(mode="ai")
    r = await c.post(api.av(f"/ai/offers/{offer['id']}/reject"), headers=api.admin)
    assert r.json()["status"] == "rejected"
    assert (await quote()).json()["subtotal"] == price


async def test_level_4_without_approval_goes_live(api: Api) -> None:
    c = api.client
    fries = api.items["French Fries"]
    await api.venue_settings(mode="ai", ai_level=4, ai_requires_approval=False, ai_price_cap_bp=2000)
    later = (utcnow() + timedelta(minutes=100)).isoformat()
    await track(api, "French Fries", on_hand=30, low_at=5, perishable_until=later)
    offers = (await c.get(api.av("/ai"), headers=api.admin)).json()["offers"]
    assert offers[0]["status"] == "active" and offers[0]["discount_bp"] == 1000, "half the cap over 1 hour"
    kiosk = await api.device("Kiosk 1", "kiosk")
    q = (await c.post("/v1/orders/quote", headers=kiosk, json={"items": [api.line("French Fries")]})).json()
    assert q["subtotal"] == fries["price"] - fries["price"] // 10
