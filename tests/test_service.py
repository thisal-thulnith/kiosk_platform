"""Table lock for pay-at-cashier, and guest calls for staff (call waiter, request bill, help)."""

from tests.conftest import Api


async def test_table_locked_until_waiting_order_is_paid(api: Api) -> None:
    c = api.client
    table = await api.device("Table 5", "table", table_ref="T5")
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=till, json={"opening_float": 0})
    cart = {"items": [api.line("Lime Juice")]}

    first = (await c.post("/v1/orders", headers=table, json=cart)).json()
    locked = await c.post("/v1/orders", headers=table, json=cart)
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "table_locked"
    assert first["token"] in locked.json()["error"]["message"]
    # A second screen on the same table is locked too.
    other = await api.device("Table 5b", "table", table_ref="T5")
    assert (await c.post("/v1/orders", headers=other, json=cart)).status_code == 409
    # Staff can still order for the table (waiter assist).
    waiter = await api.login(await api.device("Handheld", "waiter"), "Priya", "3333")
    staff_order = await c.post("/v1/orders", headers=waiter, json={**cart, "table_ref": "T5"})
    assert staff_order.status_code == 201, staff_order.text
    await c.post(f"/v1/orders/{staff_order.json()['id']}/cancel", headers=waiter, json={"reason": "test"})

    # Paid at the cashier -> the table is free again.
    paid = await c.post(
        f"/v1/orders/{first['id']}/payments/cash", headers=till, json={"tendered": first["total"]}
    )
    assert paid.status_code == 201, paid.text
    assert (await c.post("/v1/orders", headers=table, json=cart)).status_code == 201


async def test_call_waiter_and_request_bill(api: Api) -> None:
    c = api.client
    table = await api.device("Table 5", "table", table_ref="T5")
    kiosk = await api.device("Kiosk 1", "kiosk")
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")

    r = await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})
    assert r.status_code == 201 and r.json()["where"] == "Table T5" and r.json()["status"] == "open"
    again = await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})
    assert again.json()["id"] == r.json()["id"], "pressing twice pages staff once"
    bill = await c.post("/v1/service-requests", headers=table, json={"kind": "request_bill"})
    assert bill.status_code == 201
    assert (await c.post("/v1/service-requests", headers=table, json={"kind": "help"})).status_code == 403
    assert (
        await c.post("/v1/service-requests", headers=kiosk, json={"kind": "call_waiter"})
    ).status_code == 403
    help_ = await c.post("/v1/service-requests", headers=kiosk, json={"kind": "help"})
    assert help_.json()["where"] == "Kiosk 1"

    staff_view = (await c.get("/v1/service-requests", headers=till)).json()
    assert {x["kind"] for x in staff_view} == {"call_waiter", "request_bill", "help"}
    guest_view = (await c.get("/v1/service-requests", headers=table)).json()
    assert {x["kind"] for x in guest_view} == {"call_waiter", "request_bill"}

    # Guests cannot answer requests; staff acknowledge, then close.
    assert (await c.post(f"/v1/service-requests/{r.json()['id']}/ack", headers=table)).status_code == 403
    ack = (await c.post(f"/v1/service-requests/{r.json()['id']}/ack", headers=till)).json()
    assert ack["status"] == "acknowledged" and ack["acknowledged_at"]
    done = (await c.post(f"/v1/service-requests/{r.json()['id']}/done", headers=till)).json()
    assert done["status"] == "done"
    assert (await c.post(f"/v1/service-requests/{r.json()['id']}/done", headers=till)).status_code == 409
    # After it is done, the guest can call again.
    new = await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})
    assert new.json()["id"] != r.json()["id"]
