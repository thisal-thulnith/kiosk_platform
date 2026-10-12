"""Dine-in: open tabs (rounds, pay at the end), waiter serve, and the table map."""

from tests.conftest import Api


async def test_tab_rounds_go_to_kitchen_and_add_up(api: Api) -> None:
    c = api.client
    await api.venue_settings(dine_in_mode="tab")
    table = await api.device("Table 3", "table", table_ref="T3")
    kds = await api.device("Kitchen", "kds")
    me = (await c.get("/v1/devices/me", headers=table)).json()
    assert me["venue"]["dine_in_mode"] == "tab"

    first = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Chicken Burger")]})).json()
    assert first["is_tab"] and first["status"] == "in_kitchen" and first["payment_status"] == "unpaid"
    assert first["expires_at"] is None, "a tab does not expire"
    await c.post(f"/v1/kds/orders/{first['id']}/bump", headers=kds)

    second = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice", 2)]})).json()
    assert second["id"] == first["id"], "the next round goes on the same bill"
    assert second["status"] == "in_kitchen", "ready again goes back to cooking for the new round"
    assert [i["name"]["en"] for i in second["items"]] == ["Chicken Burger", "Lime Juice"]
    both = [api.line("Chicken Burger"), api.line("Lime Juice", 2)]
    quote = (await c.post("/v1/orders/quote", headers=table, json={"items": both})).json()
    assert second["total"] == quote["total"], "taxes are recalculated over the whole bill"

    tickets = (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"]
    assert [i["name"]["en"] for i in tickets[0]["items"] if i["kds_status"] == "queued"] == ["Lime Juice"]

    # Paying: while the QR is waiting, no new round can be added.
    qr = (await c.post(f"/v1/orders/{first['id']}/payments/lankaqr", headers=table)).json()["payment"]
    r = await c.post("/v1/orders", headers=table, json={"items": [api.line("Iced Milo")]})
    assert r.json()["error"]["code"] == "bill_being_paid"
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    paid = (await c.get(f"/v1/orders/{first['id']}", headers=table)).json()
    assert paid["payment_status"] == "paid" and paid["invoice_number"]
    # After the bill is paid, the next order starts a new tab.
    again = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Iced Milo")]})).json()
    assert again["id"] != first["id"] and again["is_tab"]


async def test_waiter_serve_on_a_tab(api: Api) -> None:
    c = api.client
    await api.venue_settings(dine_in_mode="tab", serve_mode="waiter")
    table = await api.device("Table 4", "table", table_ref="T4")
    kds = await api.device("Kitchen", "kds")
    status = await api.device("Board", "status")
    waiter = await api.login(await api.device("Handheld", "waiter"), "Priya", "3333")

    # The waiter orders for the table (it joins the table's tab) and can hold a course.
    o = (
        await c.post(
            "/v1/orders", headers=waiter, json={"items": [api.line("French Fries")], "table_ref": "T4"}
        )
    ).json()
    r = await c.post(
        "/v1/orders",
        headers=waiter,
        json={"items": [{**api.line("Devilled Chicken"), "hold": True}], "table_ref": "T4"},
    )
    assert r.json()["id"] == o["id"] and r.json()["items"][1]["kds_status"] == "held"
    await c.post(f"/v1/orders/{o['id']}/fire", headers=waiter)
    await c.post(f"/v1/kds/orders/{o['id']}/bump", headers=kds)
    ready = (await c.get(f"/v1/orders/{o['id']}", headers=table)).json()
    assert ready["status"] == "ready"
    assert (await c.post(f"/v1/orders/{o['id']}/served", headers=table)).status_code == 401, (
        "guests can't mark served"
    )

    served = (await c.post(f"/v1/orders/{o['id']}/served", headers=waiter)).json()
    assert served["status"] == "ready" and served["served_at"], "an unpaid tab stays open after serving"
    assert (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"] == [], "served food leaves the KDS"
    assert (await c.get("/v1/status-board", headers=status)).json()["ready"] == []

    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=till, json={"opening_float": 0})
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=till, json={"tendered": served["total"]})
    assert r.status_code == 201, r.text
    paid = r.json()
    assert paid["order"]["status"] == "completed", "paying a served tab finishes it"


async def test_table_map(api: Api) -> None:
    c = api.client
    t1 = await api.device("Table 1", "table", table_ref="T1")
    await api.device("Table 2", "table", table_ref="T2")
    t3 = await api.device("Table 3", "table", table_ref="T3")
    kds = await api.device("Kitchen", "kds")
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    assert (await c.get("/v1/tables", headers=t1)).status_code == 403

    await c.post("/v1/orders", headers=t1, json={"items": [api.line("Lime Juice")]})  # waiting for payment
    await c.post("/v1/service-requests", headers=t3, json={"kind": "call_waiter"})
    tables = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=till)).json()}
    assert [t for t in tables] == ["T1", "T2", "T3"]
    assert tables["T1"]["state"] == "waiting_payment" and tables["T1"]["open_total"] > 0
    assert tables["T2"]["state"] == "free"
    assert tables["T3"]["state"] == "calling"

    await c.post("/v1/shifts/open", headers=till, json={"opening_float": 0})
    order = tables["T1"]["orders"][0]
    await c.post(f"/v1/orders/{order['id']}/payments/cash", headers=till, json={"tendered": order["total"]})
    assert {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=till)).json()}["T1"][
        "state"
    ] == "cooking"
    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    assert {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=till)).json()}["T1"][
        "state"
    ] == "ready"
