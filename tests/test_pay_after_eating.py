"""Pay after eating: one check per table, rounds from the table and the POS, the guest asks for the
bill, the waiter prints it, collects cash with change at the table (their own cash bag) and the
table closes."""

import os

from kiosk.config import settings
from tests.conftest import Api


async def test_waiter_brings_the_bill_and_collects_cash(api: Api) -> None:
    c = api.client
    await api.venue_settings(dine_in_mode="tab")
    table = await api.device("Table T7", "table", table_ref="T7")
    first = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Chicken Burger")]})).json()
    assert first["is_tab"] and first["status"] == "in_kitchen", "after eating: cooks at once, pays later"

    # The POS adds a round to the same check (a guest asked at the counter).
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    r = await c.post("/v1/orders", headers=pos, json={"items": [api.line("Lime Juice")], "table_ref": "T7"})
    assert r.json()["id"] == first["id"], "one check per table"
    check = r.json()

    # The guest asks for the bill; staff see it.
    await c.post("/v1/service-requests", headers=table, json={"kind": "request_bill"})
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")  # role: waiter
    tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=waiter)).json()}
    assert tmap["T7"]["state"] == "bill" and tmap["T7"]["open_total"] == check["total"]

    bill = (await c.get("/v1/tables/T7/bill", headers=waiter)).json()
    assert bill["due"] == check["total"] and len(bill["lines"]) == 2
    printed = (await c.post("/v1/tables/T7/bill", headers=waiter)).json()
    assert printed["printed"]
    assert any("bill-T7" in name for name in os.listdir(settings.print_dir)), "the bill slip printed"
    assert (await c.post("/v1/tables/T7/bill", headers=table)).status_code == 403, "staff only"

    # Cash at the table: Rs 5,000 note, change given; the waiter's cash bag opens by itself.
    r = await c.post(f"/v1/orders/{check['id']}/payments/cash", headers=waiter, json={"tendered": 500000})
    assert r.status_code == 201, r.text
    paid = r.json()
    assert paid["order"]["payment_status"] == "paid"
    assert paid["payment"]["change_given"] == 500000 - check["total"]
    bag = (await c.get("/v1/shifts/current", headers=waiter)).json()
    assert bag["opening_float"] == 0 and bag["live"]["expected_cash"] == check["total"], "what to hand over"
    r = await c.get("/v1/tables/T7/bill", headers=waiter)
    assert r.json()["error"]["code"] == "nothing_to_pay"


async def test_pos_order_for_a_pay_first_table(api: Api) -> None:
    c = api.client
    pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    o = (
        await c.post("/v1/orders", headers=pos, json={"items": [api.line("Lime Juice")], "table_ref": "T9"})
    ).json()
    assert o["channel"] == "table" and o["table_ref"] == "T9" and o["token"].startswith("T")
