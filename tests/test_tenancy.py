"""Multi-tenancy: the platform creates restaurants; each restaurant only ever sees its own data."""

from typing import Any

from tests.conftest import Api

NEW = {
    "company_name": "Ocean Grill (Pvt) Ltd",
    "venue_name": "Ocean Grill Galle",
    "venue_code": "OCEAN",
    "owner_email": "Owner@Ocean.lk",
    "owner_password": "ocean-pass-1",
    "manager_pin": "4321",
    "sample_menu": True,
}


async def platform_headers(api: Api) -> dict[str, str]:
    r = await api.client.post(
        "/v1/platform/auth/login", json={"email": "platform@kiosk.lk", "password": "platform12345"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def admin_login(api: Api, email: str, password: str) -> dict[str, str]:
    r = await api.client.post("/v1/admin/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def new_restaurant(api: Api, **overrides: Any) -> tuple[dict[str, Any], dict[str, str]]:
    body = {**NEW, **overrides}
    r = await api.client.post("/v1/platform/tenants", headers=await platform_headers(api), json=body)
    assert r.status_code == 201, r.text
    return r.json(), await admin_login(api, body["owner_email"], body["owner_password"])


async def test_platform_creates_restaurant_with_owner_login(api: Api) -> None:
    c = api.client
    plat = await platform_headers(api)
    assert (await c.get("/v1/platform/tenants")).status_code == 401
    # A restaurant admin token is not a platform token.
    assert (await c.get("/v1/platform/tenants", headers=api.admin)).status_code == 401

    tenant, owner = await new_restaurant(api)
    assert tenant["venues"][0]["code"] == "OCEAN"
    assert tenant["admins"] == [{"email": "owner@ocean.lk", "role": "owner", "is_active": True}]
    names = {t["name"] for t in (await c.get("/v1/platform/tenants", headers=plat)).json()}
    assert names == {"Demo Hospitality (Pvt) Ltd", "Ocean Grill (Pvt) Ltd"}

    # The new owner sees only their venue, with the sample menu and a Manager PIN.
    venues = (await c.get("/v1/admin/venues", headers=owner)).json()
    assert [v["code"] for v in venues] == ["OCEAN"]
    vid = venues[0]["id"]
    items = (await c.get(f"/v1/admin/venues/{vid}/menu/items", headers=owner)).json()
    assert len(items) == 9
    staff = (await c.get(f"/v1/admin/venues/{vid}/staff", headers=owner)).json()
    assert [(s["name"], s["role"]) for s in staff] == [("Manager", "manager")]

    # Duplicate code or email is refused.
    dup = await c.post("/v1/platform/tenants", headers=plat, json={**NEW, "owner_email": "x@y.lk"})
    assert dup.json()["error"]["code"] == "venue_code_taken"
    dup = await c.post("/v1/platform/tenants", headers=plat, json={**NEW, "venue_code": "OTHER"})
    assert dup.json()["error"]["code"] == "email_taken"


async def test_restaurants_cannot_see_each_other(api: Api) -> None:
    c = api.client
    tenant, owner = await new_restaurant(api)
    ocean = tenant["venues"][0]["id"]
    demo = api.venue_id

    for path in ("", "/devices", "/staff", "/menu/items", "/reports/sales", "/audit"):
        assert (await c.get(f"/v1/admin/venues/{demo}{path}", headers=owner)).status_code == 404, path
        assert (await c.get(f"/v1/admin/venues/{ocean}{path}", headers=api.admin)).status_code == 404, path
    r = await c.post(
        f"/v1/admin/venues/{demo}/devices/setup-here", headers=owner, json={"type": "kds", "name": "x"}
    )
    assert r.status_code in (403, 404), "never on another restaurant, and never by a restaurant"

    # A screen of one restaurant only sees its own menu and orders (set up by our installer).
    setup = await c.post(
        f"/v1/admin/venues/{ocean}/devices/setup-here",
        headers=api.installer,
        json={"type": "kiosk", "name": "Kiosk"},
    )
    kiosk = {"X-Device-Token": setup.json()["device_token"]}
    me = (await c.get("/v1/devices/me", headers=kiosk)).json()
    assert me["venue"]["id"] == ocean
    demo_order = await c.post(
        "/v1/orders",
        headers=await api.device("Demo kiosk", "kiosk"),
        json={"items": [api.line("Lime Juice")]},
    )
    assert demo_order.status_code == 201
    assert (await c.get(f"/v1/orders/{demo_order.json()['id']}", headers=kiosk)).status_code == 404
    assert (await c.get("/v1/orders", headers=kiosk)).json() == []
    # Menu item ids of another restaurant cannot be ordered.
    r = await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})
    assert r.json()["error"]["code"] == "item_not_found"


async def test_setup_screen_with_password_once(api: Api) -> None:
    c = api.client
    base = f"/v1/admin/venues/{api.venue_id}/devices"
    assert (await c.post(f"{base}/setup-here", json={"type": "kds", "name": "x"})).status_code == 401
    r = await c.post(f"{base}/setup-here", headers=api.installer, json={"type": "table", "name": "Table 9"})
    assert r.json()["error"]["code"] == "table_ref_required"

    r = await c.post(
        f"{base}/setup-here",
        headers=api.installer,
        json={"type": "table", "name": "Table 9", "table_ref": "T9"},
    )
    assert r.status_code == 200, r.text
    first = {"X-Device-Token": r.json()["device_token"]}
    device_id = r.json()["device"]["id"]
    assert r.json()["device"]["paired"] is True
    assert (await c.get("/v1/devices/me", headers=first)).json()["device"]["table_ref"] == "T9"

    # A replacement tablet takes over the same slot; the old one stops working.
    r = await c.post(f"{base}/setup-here", headers=api.installer, json={"device_id": device_id})
    second = {"X-Device-Token": r.json()["device_token"]}
    assert (await c.get("/v1/devices/me", headers=first)).status_code == 401
    assert (await c.get("/v1/devices/me", headers=second)).json()["device"]["id"] == device_id


async def test_only_owner_adds_branches(api: Api) -> None:
    c = api.client
    r = await c.post("/v1/admin/venues", headers=api.admin, json={"name": "Demo Kandy", "code": "kandy"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "KANDY"
    assert {v["code"] for v in (await c.get("/v1/admin/venues", headers=api.admin)).json()} == {
        "DEMO",
        "KANDY",
    }
    r = await c.post(
        "/v1/admin/venues", headers=api.admin, json={"name": "Bad", "code": "BAD", "timezone": "Mars/Base"}
    )
    assert r.json()["error"]["code"] == "bad_timezone"
