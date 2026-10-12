"""Paying at the table, safely: the guest says how they will pay; one person takes the payment at
a time (others see who); the waiter's receipt prints at the counter when the waiter has no printer."""

from tests.conftest import Api


async def test_pay_at_table_one_payment_at_a_time(api: Api) -> None:
    c = api.client
    await api.venue_settings(dine_in_mode="tab", serve_mode="waiter")
    table = await api.device("Table T4", "table", table_ref="T4")
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=pos, json={"opening_float": 0})
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    pos_id = (await c.get("/v1/devices/me", headers=pos)).json()["device"]["id"]
    r = await c.post(
        api.av("/printers"),
        headers=api.installer,
        json={"name": "Counter printer", "connection": "file", "roles": ["receipt"], "device_id": pos_id},
    )
    assert r.status_code == 201, r.text

    o = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    bill = (
        await c.post(
            "/v1/service-requests",
            headers=table,
            json={"kind": "request_bill", "order_id": o["id"], "pay_with": "cash"},
        )
    ).json()
    assert bill["pay_with"] == "cash"
    again = await c.post(
        "/v1/service-requests", headers=table, json={"kind": "request_bill", "pay_with": "card"}
    )
    assert again.json()["id"] == bill["id"] and again.json()["pay_with"] == "card", "changed their mind"
    tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=waiter)).json()}
    assert tmap["T4"]["requests"][0]["pay_with"] == "card"

    # The waiter prints the bill: no printer on the phone, so it comes out at the counter.
    printed = (await c.post("/v1/tables/T4/bill", headers=waiter)).json()
    assert printed["printed_at"] == ["Counter printer"], printed

    # The waiter starts taking the payment: the bill is theirs; the cashier and the guest's QR wait.
    held = (await c.post(f"/v1/orders/{o['id']}/payment-hold", headers=waiter)).json()
    assert held["payment_hold"]["name"] == "Priya"
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=pos, json={"tendered": o["total"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "being_paid"
    assert "Priya" in r.json()["error"]["message"]
    r = await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=table)
    assert r.status_code == 409 and r.json()["error"]["code"] == "being_paid"
    assert (await c.post(f"/v1/orders/{o['id']}/payment-hold", headers=pos)).status_code == 409

    # Card on the bank's own machine at the table: the waiter types its approval code.
    r = await c.post(
        f"/v1/orders/{o['id']}/payments/card",
        headers={**waiter, "Idempotency-Key": "k1"},
        json={"approval_code": "A123"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["order"]["payment_status"] == "paid" and body["order"]["payment_hold"] is None
    assert body["printed_at"] == ["Counter printer"], "the receipt waits at the counter"
    # The same request again (a network retry) does not charge twice.
    r2 = await c.post(
        f"/v1/orders/{o['id']}/payments/card",
        headers={**waiter, "Idempotency-Key": "k1"},
        json={"approval_code": "A123"},
    )
    assert r2.json()["payment"]["id"] == body["payment"]["id"]
    paid = (await c.get(f"/v1/orders/{o['id']}", headers=pos)).json()
    assert len([p for p in paid["payments"] if p["status"] == "succeeded"]) == 1


async def test_hold_expires_and_can_be_released(api: Api) -> None:
    c = api.client
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=pos, json={"opening_float": 0})
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    o = (await c.post("/v1/orders", headers=pos, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{o['id']}/payment-hold", headers=waiter)
    assert (await c.delete(f"/v1/orders/{o['id']}/payment-hold", headers=pos)).json()["payment_hold"], (
        "not theirs"
    )
    assert (await c.delete(f"/v1/orders/{o['id']}/payment-hold", headers=waiter)).json()[
        "payment_hold"
    ] is None
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=pos, json={"tendered": o["total"]})
    assert r.status_code == 201
