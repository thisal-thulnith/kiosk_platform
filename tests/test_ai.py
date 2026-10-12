"""AI Autonomous Mode levels 0-3 with guardrails: off in Manual, learned pairings, busy-kitchen
behaviour, decision log, and prices never changed. Level 4 (deal prices) is in test_inventory."""

from typing import Any

import pytest

from kiosk.realtime.hub import hub
from tests.conftest import Api


async def pay_cash(api: Api, till: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    c = api.client
    o = (await c.post("/v1/orders", headers=till, json={"items": items})).json()
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=till, json={"tendered": o["total"]})
    assert r.status_code == 201, r.text
    return r.json()["order"]


async def cashier(api: Api) -> dict[str, str]:
    t = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 0})
    return t


async def set_prep(api: Api, name: str, minutes: int) -> None:
    item = api.items[name]
    body = {
        k: item[k] for k in ("category_id", "name", "price", "station", "tax_category", "modifier_groups")
    }
    r = await api.client.put(
        api.av(f"/menu/items/{item['id']}"), headers=api.admin, json={**body, "prep_minutes": minutes}
    )
    assert r.status_code == 200, r.text


async def test_manual_mode_is_off_and_bad_levels_are_refused(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    p = (await c.get("/v1/ai/policy", headers=kiosk)).json()
    assert p["mode"] == "manual" and p["active"] is False and p["highlights"] == [] and p["upsell"] == {}
    r = await c.patch(api.av(), headers=api.admin, json={"settings": {"mode": "ai", "ai_level": 5}})
    assert r.json()["error"]["code"] == "bad_setting"
    r = await c.patch(api.av(), headers=api.admin, json={"settings": {"mode": "robot"}})
    assert r.json()["error"]["code"] == "bad_setting"


async def test_level_2_learns_pairings_from_orders(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    for _ in range(2):
        await pay_cash(api, till, [api.line("Chicken Burger"), api.line("French Fries")])
    await pay_cash(api, till, [api.line("Chicken Kottu", 1, ["Mild"]), api.line("Lime Juice")])
    await api.venue_settings(mode="ai", ai_level=2)
    kiosk = await api.device("Kiosk 1", "kiosk")
    p = (await c.get("/v1/ai/policy", headers=kiosk)).json()
    assert p["active"] and p["level"] == 2
    burger, fries = api.items["Chicken Burger"]["id"], api.items["French Fries"]["id"]
    assert p["upsell"][burger] == [fries], "bought together twice"
    assert api.items["Lime Juice"]["id"] not in p["upsell"].get(api.items["Chicken Kottu"]["id"], []), (
        "once is not enough"
    )
    assert "insights" not in p, "insights are for staff, not guests"
    assert p["highlights"] == [], "level 2 does not reorder screens"


async def test_level_3_busy_kitchen_quick_items_and_wait(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    await set_prep(api, "Lime Juice", 2)
    await set_prep(api, "Devilled Chicken", 25)
    await api.venue_settings(mode="ai", ai_level=3, kitchen_cooks=1, kds_warn_minutes=1, kds_late_minutes=2)
    for _ in range(3):
        await pay_cash(api, till, [api.line("Devilled Chicken")])  # stays in the kitchen: busy
    kiosk = await api.device("Kiosk 1", "kiosk")
    p = (await c.get("/v1/ai/policy", headers=kiosk)).json()
    lime, devilled = api.items["Lime Juice"]["id"], api.items["Devilled Chicken"]["id"]
    assert lime in p["fast"] and devilled in p["slow"]
    assert p["highlights"][0] == lime or lime in p["highlights"]
    assert p["wait_extra_minutes"] == 10, "overloaded kitchen shows a longer wait"
    # Prices are never changed by levels 0-3.
    q = (await c.post("/v1/orders/quote", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    assert q["subtotal"] == api.items["Lime Juice"]["price"]

    owner = (await c.get(api.av("/ai"), headers=api.admin)).json()
    assert any("Kitchen is overloaded" in i and "Devilled Chicken" in i for i in owner["insights"])
    kinds = [x["kind"] for x in owner["log"]]
    assert "policy" in kinds and "mode" in kinds
    assert any("quick items first" in x["reason"] for x in owner["log"] if x["kind"] == "policy")

    # Kill switch: back to Manual, everything is off at once.
    await api.venue_settings(mode="manual")
    p = (await c.get("/v1/ai/policy", headers=kiosk)).json()
    assert p["active"] is False and p["fast"] == [] and p["wait_extra_minutes"] == 0


async def test_settings_change_is_pushed_to_screens(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append(type_)
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    await api.venue_settings(mode="ai")
    assert "venue.settings" in sent
