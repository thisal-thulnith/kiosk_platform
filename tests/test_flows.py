import os
from datetime import timedelta

from sqlalchemy import update

from kiosk.config import settings
from kiosk.infra.db import session_factory
from kiosk.infra.models import Order, utcnow
from kiosk.services import orders as order_svc
from kiosk.services.uow import UnitOfWork
from tests.conftest import Api


async def test_cashier_takeaway_cash_flow_rule_a(api: Api) -> None:
    c = api.client
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    kds = await api.device("Kitchen", "kds")

    cart = {"items": [api.line("Chicken Kottu", 2, ["Spicy", "Extra egg"]), api.line("Lime Juice")]}
    q = (await c.post("/v1/orders/quote", headers=till, json=cart)).json()
    # 2 x (1200 + 100) + 350 = 2950.00; SC 295.00; VAT 18% of 3245.00 = 584.10
    assert (q["subtotal"], q["total"]) == (295_000, 295_000 + 29_500 + 58_410)

    order = (await c.post("/v1/orders", headers=till, json=cart)).json()
    assert order["status"] == "placed" and order["payment_status"] == "unpaid"
    assert order["token"].startswith("A") and order["total"] == q["total"]

    # Rule A: nothing in the kitchen until paid
    assert (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"] == []

    r = await c.post(f"/v1/orders/{order['id']}/payments/cash", headers=till, json={"tendered": 400_000})
    assert r.json()["error"]["code"] == "no_open_shift"
    shift = (await c.post("/v1/shifts/open", headers=till, json={"opening_float": 500_000})).json()

    r = await c.post(f"/v1/orders/{order['id']}/payments/cash", headers=till, json={"tendered": 400_000})
    assert r.status_code == 201, r.text
    paid = r.json()
    assert paid["payment"]["change_given"] == 400_000 - order["total"]
    assert paid["order"]["payment_status"] == "paid"
    assert paid["order"]["status"] == "in_kitchen"
    detail = (await c.get(f"/v1/orders/{order['id']}", headers=till)).json()
    assert detail["invoice_number"] == "DEMO-00000001"
    assert any("receipt" in f for f in os.listdir(settings.print_dir))

    tickets = (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"]
    assert len(tickets) == 1 and tickets[0]["colour"] == "green"
    summary = (await c.get("/v1/kds/summary", headers=kds, params={"station": "wok"})).json()
    assert summary["to_cook"] == [{"name": "Chicken Kottu", "quantity": 2}]

    board = await api.device("Board", "status")
    assert (await c.get("/v1/status-board", headers=board)).json()["preparing"][0]["token"] == order["token"]

    # Wok cooks item 1, bar bumps its station, then the order is ready
    kottu = next(i for i in order["items"] if i["station"] == "wok")
    await c.post(f"/v1/kds/orders/{order['id']}/items/{kottu['id']}/start", headers=kds)
    r = await c.post(f"/v1/kds/orders/{order['id']}/items/{kottu['id']}/done", headers=kds)
    assert r.json()["status"] == "in_kitchen"
    r = await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds, json={"station": "bar"})
    assert r.json()["status"] == "ready"
    assert (await c.get("/v1/status-board", headers=board)).json()["ready"][0]["token"] == order["token"]

    # Recall brings the bar ticket back
    r = await c.post("/v1/kds/recall", headers=kds, json={"station": "bar"})
    assert r.json()["status"] == "in_kitchen"
    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds, json={"station": "bar"})

    r = await c.post(f"/v1/orders/{order['id']}/complete", headers=till)
    assert r.json()["status"] == "completed"

    closed = (
        await c.post(
            f"/v1/shifts/{shift['id']}/close", headers=till, json={"counted_cash": 500_000 + order["total"]}
        )
    ).json()
    assert closed["variance"] == 0

    report = (await c.get(api.av("/reports/sales"), headers=api.admin)).json()
    assert report["orders"] == 1 and report["gross_total"] == order["total"]
    assert report["tax_by_code"] == {"SC": 29_500, "VAT": 58_410}
    assert report["top_items"][0] == {"name": "Chicken Kottu", "quantity": 2, "revenue": 260_000}


async def test_kiosk_rule_b_qr_payment(api: Api) -> None:
    c = api.client
    await api.venue_settings(release_rule="B")
    kiosk = await api.device("Kiosk 1", "kiosk")
    kds = await api.device("Kitchen", "kds")

    order = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("French Fries")]})).json()
    assert order["token"].startswith("K")
    assert order["status"] == "in_kitchen" and order["payment_status"] == "unpaid"

    r = await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    assert r.json()["status"] == "ready"
    r = await c.post(f"/v1/orders/{order['id']}/complete", headers=kds)
    assert r.json()["error"]["code"] == "unpaid"

    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()
    ref = qr["payment"]["gateway_ref"]
    assert qr["payment"]["qr_payload"].startswith("LANKAQR|MOCK")
    again = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()
    assert again["payment"]["id"] == qr["payment"]["id"]  # same QR re-shown

    bad = await c.post(
        "/v1/payments/gateway/callback", content=b'{"gateway_ref": "x"}', headers={"X-Signature": "nope"}
    )
    assert bad.status_code == 401

    r = await c.post(f"/v1/dev/mock-gateway/{ref}/succeeded")
    assert r.json()["payment_status"] == "paid"
    r = await c.post(f"/v1/dev/mock-gateway/{ref}/succeeded")  # duplicate callback
    assert r.status_code == 200 and len(r.json()["payments"]) == 1

    r = await c.post(f"/v1/orders/{order['id']}/complete", headers=kds)
    assert r.json()["status"] == "completed"


async def test_unpaid_orders_expire_and_late_qr_is_refunded(api: Api) -> None:
    c = api.client
    table = await api.device("T7", "table", table_ref="7")
    order = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    assert order["token"].startswith("T") and order["table_ref"] == "7"
    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=table)).json()

    async with session_factory()() as s:
        await s.execute(update(Order).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()
        uow = UnitOfWork(s)
        expired = await order_svc.expire_due(uow)
        await uow.commit()
    assert [o.id for o in expired] == [order["id"]]

    # The guest paid anyway after expiry: the money is accepted and refunded automatically.
    r = await c.post(f"/v1/dev/mock-gateway/{qr['payment']['gateway_ref']}/succeeded")
    body = r.json()
    assert body["status"] == "expired"
    assert [p["kind"] for p in body["payments"]] == ["charge", "refund"]


async def test_idempotent_order_create(api: Api) -> None:
    kiosk = await api.device("Kiosk", "kiosk")
    body = {"items": [api.line("Iced Milo")]}
    h = {**kiosk, "Idempotency-Key": "abc-123"}
    first = await api.client.post("/v1/orders", headers=h, json=body)
    second = await api.client.post("/v1/orders", headers=h, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = (await api.client.get("/v1/orders", headers=kiosk)).json()
    assert len(listed) == 1


async def test_sold_out_and_modifier_rules(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk", "kiosk")
    kds = await api.device("Kitchen", "kds")

    r = await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Chicken Kottu")]})
    assert r.json()["error"]["code"] == "bad_modifiers"  # spice level is required

    burger = api.items["Chicken Burger"]["id"]
    r = await c.put(f"/v1/menu/items/{burger}/availability", headers=kds, json={"is_available": False})
    assert r.status_code == 200
    r = await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Chicken Burger")]})
    assert r.json()["error"]["code"] == "item_unavailable"
    menu = (await c.get("/v1/menu", headers=kiosk)).json()
    flags = {i["name"]["en"]: i["is_available"] for cat in menu["categories"] for i in cat["items"]}
    assert flags["Chicken Burger"] is False and flags["French Fries"] is True

    r = await c.put(f"/v1/menu/items/{burger}/availability", headers=kiosk, json={"is_available": True})
    assert r.status_code == 403  # guests cannot change stock


async def test_edit_before_kitchen_and_guest_permissions(api: Api) -> None:
    c = api.client
    t1 = await api.device("T1", "table", table_ref="1")
    t2 = await api.device("T2", "table", table_ref="2")
    order = (await c.post("/v1/orders", headers=t1, json={"items": [api.line("Lime Juice")]})).json()

    r = await c.put(f"/v1/orders/{order['id']}/items", headers=t2, json={"items": [api.line("Iced Milo")]})
    assert r.status_code == 403
    r = await c.put(f"/v1/orders/{order['id']}/items", headers=t1, json={"items": [api.line("Iced Milo", 2)]})
    assert r.json()["subtotal"] == 80_000

    r = await c.post(f"/v1/orders/{order['id']}/cancel", headers=t1, json={"reason": "changed mind"})
    assert r.json()["status"] == "cancelled"


async def test_void_needs_manager_and_refunds_cash(api: Api) -> None:
    c = api.client
    dev = await api.device("Till", "cashier")
    till = await api.login(dev, "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=till, json={"opening_float": 0})
    order = (await c.post("/v1/orders", headers=till, json={"items": [api.line("French Fries")]})).json()
    await c.post(f"/v1/orders/{order['id']}/payments/cash", headers=till, json={"tendered": order["total"]})

    r = await c.post(f"/v1/orders/{order['id']}/void", headers=till, json={"reason": "burnt"})
    assert r.status_code == 403
    manager = await api.login(dev, "Kamala", "9999")
    r = await c.post(f"/v1/orders/{order['id']}/void", headers=manager, json={"reason": "burnt"})
    body = r.json()
    assert body["status"] == "voided" and body["payment_status"] == "refunded"

    current = (await c.get("/v1/shifts/current", headers=manager)).json()
    assert current["live"]["expected_cash"] == 0
    audit = (await c.get(api.av("/audit"), headers=api.admin)).json()
    assert {"order.void", "order.refund"} <= {a["action"] for a in audit}


async def test_pin_lockout(api: Api) -> None:
    dev = await api.device("Till", "cashier")
    for _ in range(5):
        r = await api.client.post(
            "/v1/staff/pin-login", headers=dev, json={"staff_id": api.staff_ids["Nimal"], "pin": "0000"}
        )
        assert r.status_code == 401
    r = await api.client.post(
        "/v1/staff/pin-login", headers=dev, json={"staff_id": api.staff_ids["Nimal"], "pin": "1111"}
    )
    assert r.status_code == 423


async def test_lookup_by_token_and_table(api: Api) -> None:
    c = api.client
    table = await api.device("T9", "table", table_ref="9")
    till = await api.login(await api.device("Till", "cashier"), "Nimal", "1111")
    order = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    for code in (order["id"], order["token"].lower(), "9"):
        assert (await c.get("/v1/orders/lookup", headers=till, params={"code": code})).json()["id"] == order[
            "id"
        ]


async def test_device_auth_required(api: Api) -> None:
    assert (await api.client.get("/v1/menu")).status_code == 401
    assert (await api.client.get("/v1/menu", headers={"X-Device-Token": "nope"})).status_code == 401
    r = await api.client.post("/v1/devices/pair", json={"code": "000000"})
    assert r.json()["error"]["code"] == "bad_pairing_code"


async def test_admin_lists_own_venues_and_screens_are_served(api: Api) -> None:
    c = api.client
    venues = (await c.get("/v1/admin/venues", headers=api.admin)).json()
    assert [v["id"] for v in venues] == [api.venue_id]
    assert (await c.get("/v1/admin/venues")).status_code == 401

    # Every screen and console has a clean address (the React build, frontend/ -> web/ui).
    for page in ("pos", "waiter", "kitchen", "kiosk", "board", "owner", "setup", "menu"):
        r = await c.get(f"/demo/{page}")
        assert r.status_code == 200 and "<!doctype html>" in r.text.lower(), page
