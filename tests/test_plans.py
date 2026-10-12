"""Packages, modules and screen limits (Product Details: Pack 1/2/3, Custom, Hotel)."""

import pytest

from kiosk.domain.modules import PlanError, build_plan, has_module, quote
from tests.conftest import Api
from tests.test_tenancy import NEW, admin_login, platform_headers


def test_pack_tiers_match_the_product_details() -> None:
    p = build_plan("pack2", "starter")
    assert p["screens"] == {"cashier": 1, "kds": 1, "table": 6}, "the status board is optional"
    assert {"R-CORE", "R-KDS", "R-CASH", "R-TABLE", "R-PAY"} <= set(p["modules"])
    assert "R-WAITER" not in p["modules"]
    p = build_plan("pack2", "standard")
    assert p["screens"] == {"cashier": 1, "kds": 2, "table": 12}
    p = build_plan("pack2", "premium")
    assert p["screens"] == {"cashier": 2, "kds": 2, "table": 20}
    assert {"R-AI", "R-LOYAL", "R-VOICE"} <= set(p["modules"])
    p = build_plan("pack1", "standard")
    assert p["screens"] == {"kds": 2, "kiosk": 2} and "R-VOICE" in p["modules"]
    with_board = build_plan("pack1", "standard", flows=["status_display"])
    assert with_board["screens"]["status"] == 1 and "R-STATUS" in with_board["modules"]
    hybrid = build_plan("pack3", "premium")
    assert hybrid["screens"]["kiosk"] == 3 and hybrid["screens"]["table"] == 20
    assert {"R-SELF", "R-TABLE", "R-CASH"} <= set(hybrid["modules"])


def test_addons_and_extra_screens() -> None:
    p = build_plan("pack2", "starter", add=["R-WAITER"], screens={"table": 4})
    assert p["screens"]["table"] == 10 and p["screens"]["waiter"] == 1, (
        "a module that sells a screen gets one"
    )
    with pytest.raises(PlanError) as e:
        build_plan("pack1", "starter", add=["R-TABLE"])
    assert e.value.code == "not_an_addon"
    with pytest.raises(PlanError) as e:
        build_plan("pack2", "gold")
    assert e.value.code == "unknown_tier"


def test_builder_rules() -> None:
    with pytest.raises(PlanError) as e:
        build_plan("custom", modules=["R-SELF", "R-PAY"])
    assert e.value.code == "module_required"
    with pytest.raises(PlanError) as e:
        build_plan("custom", modules=["R-CORE", "R-KDS", "R-BRIDGE", "R-POS"])
    assert e.value.code == "bridge_or_pos"
    with pytest.raises(PlanError) as e:
        build_plan("custom", modules=["R-CORE", "R-KDS"], screens={"table": 5})
    assert e.value.code == "module_missing"
    lite = build_plan("custom", modules=["R-CORE", "R-KDS", "R-CASH", "R-PAY"], screens={"kds": 1})
    assert lite["screens"] == {"cashier": 1, "kds": 1}
    assert any("R-STATUS" in w for w in lite["warnings"])
    assert any("2 months" in w for w in build_plan("pack2", "premium")["warnings"])
    with pytest.raises(PlanError) as e:
        build_plan("hotel", modules=["H-DINE"])
    assert e.value.code == "module_required"
    hotel = build_plan("hotel", modules=["H-CORE", "H-DINE", "H-KDS"], screens={"room": 20})
    assert hotel["screens"] == {"kds": 1, "room": 20}
    assert has_module(None, "R-AI") and not has_module(lite, "R-AI")


def test_quote_uses_price_book() -> None:
    plan = build_plan("pack2", "starter")
    q = quote(
        plan,
        {
            "screen:table": {"monthly": 150_000, "once": 9_000_000},
            "module:R-CORE": {"monthly": 1_000_000, "once": 0},
        },
    )
    assert q["monthly_total"] == 6 * 150_000 + 1_000_000
    assert q["once_total"] == 6 * 9_000_000
    assert "screen:cashier" in q["missing_prices"]


async def test_restaurant_with_package_gets_slots_and_limits(api: Api) -> None:
    c = api.client
    plat = await platform_headers(api)
    catalog = (await c.get("/v1/platform/catalog", headers=plat)).json()
    assert set(catalog["packs"]) == {"pack1", "pack2", "pack3", "custom", "hotel"}

    body = {**NEW, "plan": {"pack": "pack2", "tier": "starter"}}
    r = await c.post("/v1/platform/tenants", headers=plat, json=body)
    assert r.status_code == 201, r.text
    venue = r.json()["venues"][0]
    assert venue["plan"]["tier"] == "starter" and venue["screens"] == 8  # 6 tables, POS, kitchen
    owner = await admin_login(api, NEW["owner_email"], NEW["owner_password"])
    base = f"/v1/admin/venues/{venue['id']}"

    devices = (await c.get(f"{base}/devices", headers=owner)).json()
    tables = sorted(d["table_ref"] for d in devices if d["type"] == "table")
    assert tables == ["T1", "T2", "T3", "T4", "T5", "T6"]
    usage = (await c.get(f"{base}/plan", headers=owner)).json()["usage"]
    assert usage["table"] == {"used": 6, "set_up": 0, "limit": 6}

    # Screens are set up by our installation team, not by the restaurant.
    r = await c.post(
        f"{base}/devices", headers=owner, json={"type": "table", "name": "T7", "table_ref": "T7"}
    )
    assert r.status_code == 403 and "installation team" in r.json()["error"]["message"]

    # A 7th table is refused; a kiosk is not in Pack 2 at all.
    r = await c.post(f"{base}/devices", headers=plat, json={"type": "table", "name": "T7", "table_ref": "T7"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "screen_limit"
    r = await c.post(f"{base}/devices/setup-here", headers=plat, json={"type": "kiosk", "name": "Kiosk"})
    assert r.json()["error"]["code"] == "module_not_in_plan"
    # Setting up an existing slot is fine (no new screen).
    t1 = next(d for d in devices if d["table_ref"] == "T1")
    assert (
        await c.post(f"{base}/devices/setup-here", headers=plat, json={"device_id": t1["id"]})
    ).status_code == 200

    # Disable one table -> room for another; enabling the old one again is refused.
    await c.patch(f"{base}/devices/{t1['id']}", headers=plat, json={"is_active": False})
    assert (
        await c.post(f"{base}/devices", headers=plat, json={"type": "table", "name": "T7", "table_ref": "T7"})
    ).status_code == 201
    r = await c.patch(f"{base}/devices/{t1['id']}", headers=plat, json={"is_active": True})
    assert r.json()["error"]["code"] == "screen_limit"

    # Upgrade to Standard: 12 tables, 2 kitchens, a waiter handheld; missing slots are created.
    r = await c.put(
        f"/v1/platform/venues/{venue['id']}/plan", headers=plat, json={"pack": "pack2", "tier": "standard"}
    )
    assert r.status_code == 200, r.text
    made = r.json()["slots_created"]
    assert "Kitchen 2" in made and not any(n.startswith("Waiter") for n in made)
    assert sum(n.startswith("Table") for n in made) == 6
    assert "Table T1" not in made and "Table T8" in made, "numbers of disabled tables stay reserved"
    assert r.json()["usage"]["table"] == {"used": 12, "set_up": 0, "limit": 12}


async def test_payments_module_and_quote_endpoint(api: Api) -> None:
    c = api.client
    plat = await platform_headers(api)
    no_pay = {"pack": "custom", "modules": ["R-CORE", "R-KDS", "R-SELF", "R-STATUS"]}
    r = await c.put(
        f"/v1/platform/venues/{api.venue_id}/plan", headers=plat, json={**no_pay, "create_slots": False}
    )
    assert r.status_code == 200, r.text
    kiosk = await api.device("Kiosk 1", "kiosk")
    order = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    r = await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)
    assert r.status_code == 403 and r.json()["error"]["code"] == "module_not_in_plan"

    await c.put(
        "/v1/platform/prices",
        headers=plat,
        json=[{"item": "screen:kiosk", "monthly": 500_000, "once": 45_000_000}],
    )
    q = (await c.post("/v1/platform/quote", headers=plat, json={"pack": "pack1", "tier": "premium"})).json()
    assert q["plan"]["screens"]["kiosk"] == 3
    kiosk_line = next(line for line in q["lines"] if line["item"] == "screen:kiosk")
    assert (kiosk_line["qty"], kiosk_line["monthly"], kiosk_line["once"]) == (3, 1_500_000, 135_000_000)
    bad = await c.post("/v1/platform/quote", headers=plat, json={"pack": "custom", "modules": ["R-TABLE"]})
    assert bad.json()["error"]["code"] == "module_required"


def test_equipment_brings_what_it_needs() -> None:
    plan = build_plan("custom", modules=["R-CORE", "R-KDS", "R-SELF"], screens={"kiosk": 2})
    assert "status" not in plan["screens"], "the status board is optional"
    assert plan["hardware"] == {"kiosk_printer": 2, "router": 1}

    plan = build_plan("custom", modules=["R-CORE", "R-KDS", "R-WAITER"], screens={"waiter": 1})
    # waiter -> table -> cashier -> receipt printer + cash drawer
    assert plan["screens"]["table"] == 1 and plan["screens"]["cashier"] == 1
    assert {"R-TABLE", "R-CASH"} <= set(plan["modules"])
    assert plan["hardware"]["receipt_printer"] == 1 and plan["hardware"]["cash_drawer"] == 1

    plan = build_plan("pack2", "standard", hardware={"receipt_printer": 0, "ups": 2, "kitchen_printer": 1})
    cashiers = plan["screens"]["cashier"]
    assert plan["hardware"]["receipt_printer"] == cashiers, "can't go below one per cashier"
    assert plan["hardware"]["ups"] == 2 and plan["hardware"]["kitchen_printer"] == 1
    reasons = {r["item"]: r for r in plan["requirements"]}
    assert reasons["cash_drawer"]["min"] == cashiers and "cash" in reasons["cash_drawer"]["reasons"][0]
    with pytest.raises(PlanError):
        build_plan("pack2", "starter", hardware={"toaster": 1})
