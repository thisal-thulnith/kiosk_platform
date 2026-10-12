"""The owner sees who did what: orders taken, payments collected, calls answered (and how fast),
food taken to the tables, per person and per table."""

from tests.conftest import Api


async def test_staff_and_table_report(api: Api) -> None:
    c = api.client
    tab = {"settings": {"dine_in_mode": "tab", "serve_mode": "waiter"}}
    await c.patch(api.av(""), headers=api.admin, json=tab)
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=pos, json={"opening_float": 0})
    take = (await c.post("/v1/orders", headers=pos, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{take['id']}/payments/cash", headers=pos, json={"tendered": take["total"]})

    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    table = await api.device("Table T2", "table", table_ref="T2")
    call = (await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})).json()
    await c.post(f"/v1/service-requests/{call['id']}/ack", headers=waiter)
    await c.post(f"/v1/service-requests/{call['id']}/done", headers=waiter)
    body = {"items": [api.line("Lime Juice", 2)], "table_ref": "T2"}
    o = (await c.post("/v1/orders", headers=waiter, json=body)).json()
    assert o["table_ref"] == "T2", o
    kds = await api.device("Kitchen", "kds")
    assert (await c.post(f"/v1/kds/orders/{o['id']}/bump", headers=kds, json={})).status_code == 200
    assert (await c.post(f"/v1/orders/{o['id']}/served", headers=waiter)).status_code == 200
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=waiter, json={"tendered": o["total"]})
    assert r.status_code == 201, r.text

    rep = (await c.get(api.av("/reports/staff"), headers=api.admin)).json()
    by = {r["name"]: r for r in rep["staff"]}
    priya, nimal = by["Priya"], by["Nimal"]
    assert nimal["orders_taken"] == 1 and nimal["payments"]["amount"] == take["total"]
    assert nimal["shifts"]["count"] == 1
    assert priya["orders_taken"] == 1 and priya["items_ordered"] == 2
    assert priya["payments"] == {"count": 1, "amount": o["total"], "by_method": {"cash": o["total"]}}
    assert priya["calls"]["answered"] == 1 and priya["calls"]["avg_answer_seconds"] is not None
    assert priya["served"]["count"] == 1 and priya["table_visits"] == 2 and priya["tables"] == ["T2"]
    t2 = next(t for t in rep["tables"] if t["table_ref"] == "T2")
    assert t2["orders"] == 1 and t2["revenue"] == o["total"] and t2["calls"] == 1
    assert t2["waiters"] == ["Priya"]
    assert rep["calls"]["count"] == 1 and rep["calls"]["unanswered"] == 0
    csv = (await c.get(api.av("/reports/staff.csv"), headers=api.admin)).text
    assert csv.startswith("name,role,orders_taken") and "Priya,waiter,1" in csv
