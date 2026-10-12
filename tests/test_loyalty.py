"""Loyalty: consent, points on payment, tier discounts before taxes, "your usual", PDPA export/forget."""

import pytest

from kiosk.errors import AppError
from kiosk.services.loyalty import normalize_phone
from tests.conftest import Api
from tests.test_tenancy import new_restaurant


def test_phone_numbers() -> None:
    for raw in ("0771234567", "771234567", "+94 77 123 4567", "+94-77-1234567"):
        assert normalize_phone(raw) == "+94771234567"
    with pytest.raises(AppError):
        normalize_phone("12")


async def till(api: Api) -> dict[str, str]:
    t = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 0})
    return t


async def test_join_needs_consent_and_points_on_payment(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    r = await c.post("/v1/loyalty/lookup", headers=kiosk, json={"phone": "0771234567"})
    assert r.json()["known"] is False and "delete" in r.json()["consent_text"]
    r = await c.post(
        "/v1/loyalty/join",
        headers=kiosk,
        json={"phone": "0771234567", "name": "Kamal Perera", "consent": False},
    )
    assert r.json()["error"]["code"] == "consent_required"
    r = await c.post(
        "/v1/loyalty/join",
        headers=kiosk,
        json={"phone": "0771234567", "name": "Kamal Perera", "consent": True},
    )
    member = r.json()
    assert (member["first_name"], member["points"], member["tier"]) == ("Kamal", 0, None), (
        "guests see the first name only"
    )
    assert member["next_tier"] == {"name": "Silver", "points_needed": 500}

    order = (
        await c.post(
            "/v1/orders",
            headers=kiosk,
            json={"items": [api.line("Devilled Chicken", 2)], "customer_phone": "077 123 4567"},
        )
    ).json()
    assert order["customer_id"] and order["discount_total"] == 0
    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    paid = (await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")).json()
    assert paid["points_earned"] == order["total"] // 10_000
    after = (await c.post("/v1/loyalty/lookup", headers=kiosk, json={"phone": "+94771234567"})).json()
    assert after["points"] == paid["points_earned"]
    assert [f["name"]["en"] for f in after["favorites"]] == ["Devilled Chicken"], "their usual"


async def test_tier_discount_comes_off_before_taxes(api: Api) -> None:
    c = api.client
    await api.venue_settings(loyalty_tiers=[{"name": "Silver", "min_points": 1, "discount_bp": 1000}])
    t = await till(api)
    await c.post(
        "/v1/loyalty/join", headers=t, json={"phone": "0712223334", "name": "Nuwan", "consent": True}
    )
    first = (
        await c.post(
            "/v1/orders",
            headers=t,
            json={"items": [api.line("Chicken Burger")], "customer_phone": "0712223334"},
        )
    ).json()
    await c.post(f"/v1/orders/{first['id']}/payments/cash", headers=t, json={"tendered": first["total"]})

    second = (
        await c.post(
            "/v1/orders",
            headers=t,
            json={"items": [api.line("Chicken Burger")], "customer_phone": "0712223334"},
        )
    ).json()
    price = api.items["Chicken Burger"]["price"]
    assert second["subtotal"] == price and second["discount_total"] == price // 10
    assert second["discount_label"] == "Silver member 10%"
    net = price - price // 10
    sc = round(net * 0.10)
    vat = round((net + sc) * 0.18)
    assert second["total"] == net + sc + vat, "service charge and VAT on the discounted amount"

    # Adding a member to an order that was placed without one reprices it.
    plain = (await c.post("/v1/orders", headers=t, json={"items": [api.line("Chicken Burger")]})).json()
    assert plain["discount_total"] == 0
    added = (
        await c.post(f"/v1/orders/{plain['id']}/customer", headers=t, json={"phone": "0712223334"})
    ).json()
    assert added["discount_total"] == price // 10 and added["total"] == second["total"]

    # Refund gives the points back.
    manager = await api.login(await api.device("Till 2", "cashier"), "Kamala", "9999")
    await c.post("/v1/shifts/open", headers=manager, json={"opening_float": 1_000_000})
    points_before = (await c.post("/v1/loyalty/lookup", headers=t, json={"phone": "0712223334"})).json()[
        "points"
    ]
    await c.post(f"/v1/orders/{first['id']}/refund", headers=manager, json={"reason": "cold"})
    points_after = (await c.post("/v1/loyalty/lookup", headers=t, json={"phone": "0712223334"})).json()[
        "points"
    ]
    assert points_after == points_before - first["total"] // 10_000


async def test_export_forget_and_isolation(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    await c.post(
        "/v1/loyalty/join", headers=kiosk, json={"phone": "0779998887", "name": "Shani", "consent": True}
    )
    members = (await c.get(api.av("/customers"), headers=api.admin)).json()
    shani = next(m for m in members if m["name"] == "Shani")
    assert shani["phone"] == "+94779998887" and shani["consent_at"]
    data = (await c.get(api.av(f"/customers/{shani['id']}/export"), headers=api.admin)).json()
    assert data["member"]["consent_text"] and data["orders"] == []

    # Another restaurant never sees this member.
    tenant, owner = await new_restaurant(api, venue_code="OTHER", owner_email="o@other.lk")
    other = tenant["venues"][0]["id"]
    assert (await c.get(f"/v1/admin/venues/{other}/customers", headers=owner)).json() == []
    assert (await c.get(api.av(f"/customers/{shani['id']}/export"), headers=owner)).status_code == 404

    forgotten = (await c.post(api.av(f"/customers/{shani['id']}/forget"), headers=api.admin)).json()
    assert forgotten["phone"] is None and forgotten["name"] is None and forgotten["forgotten"]
    assert (await c.post("/v1/loyalty/lookup", headers=kiosk, json={"phone": "0779998887"})).json()[
        "known"
    ] is False
    order = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    r = await c.post(f"/v1/orders/{order['id']}/customer", headers=kiosk, json={"phone": "0779998887"})
    assert r.status_code == 404


async def test_loyalty_needs_module(api: Api) -> None:
    c = api.client
    from tests.test_tenancy import platform_headers

    plan = {"pack": "pack2", "tier": "starter", "create_slots": False}
    await c.put(f"/v1/platform/venues/{api.venue_id}/plan", headers=await platform_headers(api), json=plan)
    till_ = await till(api)
    r = await c.post("/v1/loyalty/lookup", headers=till_, json={"phone": "0771234567"})
    assert r.json()["error"]["code"] == "module_not_in_plan"
