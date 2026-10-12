"""Card terminals: built-in kiosk readers and SoftPOS (tap on a staff tablet)."""

from typing import Any

from kiosk.infra.terminal import get_terminal
from tests.conftest import Api


async def configure(api: Api, device_name: str, **body: Any) -> Any:
    devices = (await api.client.get(api.av("/devices"), headers=api.admin)).json()
    device = next(d for d in devices if d["name"] == device_name)
    return await api.client.patch(api.av(f"/devices/{device['id']}"), headers=api.installer, json=body)


async def tap(api: Api, ref: str, outcome: str = "succeeded") -> dict[str, Any]:
    r = await api.client.post(f"/v1/dev/mock-terminal/{ref}/{outcome}")
    assert r.status_code == 200, r.text
    return r.json()


async def order_on(api: Api, headers: dict[str, str], item: str = "Chicken Burger") -> dict[str, Any]:
    r = await api.client.post("/v1/orders", headers=headers, json={"items": [api.line(item)]})
    assert r.status_code == 201, r.text
    return r.json()


async def test_kiosk_reader_tap_pays_and_releases(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    kds = await api.device("Kitchen", "kds")
    assert (await c.get("/v1/devices/me", headers=kiosk)).json()["payments"]["card"] is None

    r = await configure(api, "Kiosk 1", card_mode="reader")
    assert r.json()["error"]["code"] == "terminal_id_required"
    r = await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-IM30-001")
    assert r.json()["card"] == {"mode": "reader", "terminal_id": "PAX-IM30-001"}
    assert (await c.get("/v1/devices/me", headers=kiosk)).json()["payments"]["card"] == "reader"

    order = await order_on(api, kiosk)
    start = await c.post(
        f"/v1/orders/{order['id']}/payments/card-terminal", headers={**kiosk, "Idempotency-Key": "k1"}
    )
    assert start.status_code == 201, start.text
    payment = start.json()["payment"]
    assert (payment["method"], payment["status"], payment["amount"]) == ("card", "pending", order["total"])
    assert start.json()["order"]["payment_status"] == "pending"
    # Pressing "Pay by card" again re-uses the waiting terminal instead of charging twice.
    again = await c.post(
        f"/v1/orders/{order['id']}/payments/card-terminal", headers={**kiosk, "Idempotency-Key": "k2"}
    )
    assert again.json()["payment"]["id"] == payment["id"]
    # Rule A: nothing in the kitchen until the card is approved.
    assert (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"] == []

    paid = await tap(api, payment["gateway_ref"])
    assert (paid["status"], paid["payment_status"]) == ("in_kitchen", "paid")
    charge = next(p for p in paid["payments"] if p["id"] == payment["id"])
    assert charge["status"] == "succeeded" and charge["external_ref"].startswith("A")
    assert len((await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"]) == 1
    invoice = (await c.get(f"/v1/orders/{order['id']}", headers=kiosk)).json()["invoice_number"]
    assert invoice.startswith("DEMO-")

    # The processor may resend its callback: nothing changes.
    again = await tap(api, payment["gateway_ref"])
    assert again["paid_total"] == order["total"] and again["version"] == paid["version"]


async def test_declined_card_can_retry(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-1")
    order = await order_on(api, kiosk)
    first = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()[
        "payment"
    ]
    declined = await tap(api, first["gateway_ref"], "failed")
    assert (declined["status"], declined["payment_status"]) == ("placed", "unpaid")

    second = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()[
        "payment"
    ]
    assert second["id"] != first["id"]
    assert (await tap(api, second["gateway_ref"]))["payment_status"] == "paid"


async def test_softpos_only_on_staff_screens(api: Api) -> None:
    c = api.client
    await api.device("Kiosk 1", "kiosk")
    await api.device("Table 1", "table", table_ref="T1")
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    r = await configure(api, "Kiosk 1", card_mode="softpos")
    assert r.json()["error"]["code"] == "softpos_attended_only", "a kiosk has no staff: use a reader"

    assert (await configure(api, "Till 1", card_mode="softpos")).json()["card"] == {"mode": "softpos"}
    order = await order_on(api, till)
    p = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=till)).json()["payment"]
    paid = await tap(api, p["gateway_ref"])
    assert paid["payment_status"] == "paid"
    assert next(x for x in paid["payments"] if x["id"] == p["id"])["staff_id"] == api.staff_ids["Nimal"]


async def test_table_card_payments(api: Api) -> None:
    """At the table: a certified reader for the guest alone, or tap on the tablet with a waiter."""
    c = api.client
    table = await api.device("Table 1", "table", table_ref="T1")
    assert (await configure(api, "Table 1", card_mode="softpos")).json()["card"] == {"mode": "softpos"}
    order = await order_on(api, table)
    r = await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=table)
    assert r.json()["error"]["code"] == "softpos_needs_staff", "the guest alone can't tap on the tablet"
    waiter_here = await api.login(table, "Nimal", "1111")  # waiter assist: staff PIN on the table
    p = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=waiter_here)).json()
    assert (await tap(api, p["payment"]["gateway_ref"]))["payment_status"] == "paid"

    await configure(api, "Table 1", card_mode="reader", card_terminal_id="PAX-IM15-T1")
    order2 = await order_on(api, table)
    p2 = (await c.post(f"/v1/orders/{order2['id']}/payments/card-terminal", headers=table)).json()["payment"]
    assert (await tap(api, p2["gateway_ref"]))["payment_status"] == "paid", (
        "a reader works for the guest alone"
    )


async def test_screen_without_reader_is_refused(api: Api) -> None:
    table = await api.device("Table 1", "table", table_ref="T1")
    order = await order_on(api, table)
    r = await api.client.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=table)
    assert r.json()["error"]["code"] == "no_card_terminal"


async def test_switch_to_qr_and_late_card_tap_is_refunded(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-1")
    order = await order_on(api, kiosk)
    card = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()["payment"]

    # Guest changes their mind and pays by QR instead; the card attempt is cancelled.
    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    assert (await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")).json()[
        "payment_status"
    ] == "paid"

    # ...but the card tap still went through a moment later: accepted and refunded automatically.
    after = await tap(api, card["gateway_ref"])
    assert after["payment_status"] == "paid" and after["paid_total"] == order["total"]
    refund = next(p for p in after["payments"] if p["kind"] == "refund")
    assert (refund["method"], refund["amount"]) == ("card", order["total"])
    assert refund["external_ref"].startswith("MOCKCARDREFUND")


async def test_guest_cancels_waiting_card_payment(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    other = await api.device("Kiosk 2", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-1")
    order = await order_on(api, kiosk)
    card = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()["payment"]

    # Another guest screen can't cancel someone else's payment.
    r = await c.post(f"/v1/orders/{order['id']}/payments/{card['id']}/cancel", headers=other)
    assert r.status_code == 403
    r = await c.post(f"/v1/orders/{order['id']}/payments/{card['id']}/cancel", headers=kiosk)
    assert r.json()["payment"]["status"] == "cancelled" and r.json()["order"]["payment_status"] == "unpaid"
    again = await c.post(f"/v1/orders/{order['id']}/payments/{card['id']}/cancel", headers=kiosk)
    assert again.json()["error"]["code"] == "not_pending"


async def test_manager_void_refunds_through_terminal(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-1")
    manager = await api.login(await api.device("Till 1", "cashier"), "Kamala", "9999")
    order = await order_on(api, kiosk)
    card = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()["payment"]
    await tap(api, card["gateway_ref"])

    voided = (
        await c.post(f"/v1/orders/{order['id']}/void", headers=manager, json={"reason": "Wrong order"})
    ).json()
    assert (voided["status"], voided["payment_status"]) == ("voided", "refunded")
    refund = next(p for p in voided["payments"] if p["kind"] == "refund")
    assert refund["method"] == "card" and refund["external_ref"].startswith("MOCKCARDREFUND")


async def test_terminal_callback_must_be_signed(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-1")
    order = await order_on(api, kiosk)
    card = (await c.post(f"/v1/orders/{order['id']}/payments/card-terminal", headers=kiosk)).json()["payment"]
    body, _ = get_terminal().build_callback(card["gateway_ref"], "succeeded", card["amount"])
    r = await c.post("/v1/payments/terminal/callback", content=body, headers={"X-Signature": "forged"})
    assert r.status_code == 401

    # A correctly signed callback with the wrong amount is rejected too.
    wrong, sig = get_terminal().build_callback(card["gateway_ref"], "succeeded", card["amount"] - 100)
    r = await c.post("/v1/payments/terminal/callback", content=wrong, headers={"X-Signature": sig})
    assert r.json()["error"]["code"] == "amount_mismatch"

    good, sig = get_terminal().build_callback(card["gateway_ref"], "succeeded", card["amount"])
    r = await c.post("/v1/payments/terminal/callback", content=good, headers={"X-Signature": sig})
    assert r.json()["payment_status"] == "paid"
