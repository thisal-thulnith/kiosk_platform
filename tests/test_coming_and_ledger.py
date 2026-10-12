"""Who is coming to a guest's call (named, reassignable, seen by the guest), and the payment ledger
(every payment traceable: who, where, how, reference, invoice)."""

from tests.conftest import Api


async def test_coming_names_the_waiter(api: Api) -> None:
    c = api.client
    table = await api.device("Table T3", "table", table_ref="T3")
    call = (await c.post("/v1/service-requests", headers=table, json={"kind": "request_bill"})).json()
    assert call["coming"] is None
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    priya = api.staff_ids["Priya"]
    r = (await c.post(f"/v1/service-requests/{call['id']}/ack", headers=pos, json={"staff_id": priya})).json()
    assert r["status"] == "acknowledged" and r["coming"] == {"staff_id": priya, "name": "Priya"}
    mine = (await c.get("/v1/service-requests", headers=table)).json()
    assert mine[0]["coming"]["name"] == "Priya", "the guest sees who is coming"
    tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=pos)).json()}
    assert tmap["T3"]["requests"][0]["coming"] == "Priya"
    # Re-assign: the waiter's own phone takes it.
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Kamala", "9999")
    r = (await c.post(f"/v1/service-requests/{call['id']}/ack", headers=waiter)).json()
    assert r["coming"]["name"] == "Kamala"
    r = await c.post(f"/v1/service-requests/{call['id']}/ack", headers=pos, json={"staff_id": "nobody"})
    assert r.status_code == 404


async def test_payment_ledger_is_traceable(api: Api) -> None:
    c = api.client
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    await c.post("/v1/shifts/open", headers=pos, json={"opening_float": 0})
    o = (await c.post("/v1/orders", headers=pos, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=pos, json={"tendered": 100000})
    kiosk = await api.device("Kiosk 1", "kiosk")
    k = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    qr = (await c.post(f"/v1/orders/{k['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")

    led = (await c.get("/v1/payments", headers=pos)).json()
    assert led["count"] == 2 and led["total"] == o["total"] + k["total"]
    cash = next(x for x in led["lines"] if x["method"] == "cash")
    assert cash["collected_by"] == "Nimal" and cash["device"] == "POS 1" and cash["token"] == o["token"]
    assert cash["tendered"] == 100000 and cash["change_given"] == 100000 - o["total"]
    assert cash["invoice"] and len(cash["ref"]) == 8
    qrl = next(x for x in led["lines"] if x["method"] == "lankaqr")
    assert qrl["collected_by"] == "Guest (self-service)" and qrl["outside_ref"] == qr["gateway_ref"]
    assert led["by_staff"]["Nimal"] == o["total"]

    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    assert (await c.get("/v1/payments", headers=waiter)).json()["count"] == 0, "a waiter sees their own"
    owner = (await c.get(api.av("/reports/payments"), headers=api.admin)).json()
    assert owner["count"] == 2
    csv = (await c.get(api.av("/reports/payments.csv"), headers=api.admin)).text
    assert "collected_by" in csv and "Nimal" in csv and o["token"] in csv
    assert (await c.get("/v1/payments", headers=kiosk)).status_code == 403


async def test_paid_bill_answers_the_bill_call(api: Api) -> None:
    c = api.client
    table = await api.device("Table T4", "table", table_ref="T4")
    o = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    await c.post("/v1/service-requests", headers=table, json={"kind": "request_bill", "order_id": o["id"]})
    await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=waiter, json={"tendered": o["total"]})
    assert r.status_code == 201, r.text
    left = {x["kind"]: x["status"] for x in (await c.get("/v1/service-requests", headers=waiter)).json()}
    assert "request_bill" not in left or left["request_bill"] == "done", "paid: the bill call is answered"
    assert left["call_waiter"] == "open", "other calls stay"
