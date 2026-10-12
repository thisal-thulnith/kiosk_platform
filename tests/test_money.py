"""Split bill, tax ledger export, reconciliation, operations report, VAT number on receipts."""

import csv
import io
from pathlib import Path

from kiosk.config import settings
from tests.conftest import Api
from tests.test_tenancy import platform_headers


def printed_receipts() -> list[bytes]:
    return [p.read_bytes() for p in sorted(Path(settings.print_dir).glob("*receipt*.bin"))]


async def till(api: Api) -> dict[str, str]:
    t = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 0})
    return t


async def test_split_bill(api: Api) -> None:
    c = api.client
    t = await till(api)
    kds = await api.device("Kitchen", "kds")
    order = (await c.post("/v1/orders", headers=t, json={"items": [api.line("Devilled Chicken", 2)]})).json()
    half = order["total"] // 2
    r = await c.post(
        f"/v1/orders/{order['id']}/payments/cash", headers=t, json={"tendered": half, "amount": half}
    )
    assert r.status_code == 201, r.text
    part = r.json()["order"]
    assert (part["paid_total"], part["payment_status"], part["status"]) == (half, "unpaid", "placed")
    assert (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"] == [], (
        "kitchen waits for the full bill"
    )
    assert (await c.get(f"/v1/orders/{order['id']}", headers=t)).json()["invoice_number"] is None

    too_much = await c.post(
        f"/v1/orders/{order['id']}/payments/lankaqr", headers=t, json={"amount": order["total"]}
    )
    assert too_much.json()["error"]["code"] == "bad_amount"
    qr = (await c.post(f"/v1/orders/{order['id']}/payments/lankaqr", headers=t)).json()["payment"]
    assert qr["amount"] == order["total"] - half, "no amount = the rest of the bill"
    done = (await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")).json()
    assert (done["payment_status"], done["status"]) == ("paid", "in_kitchen")
    assert (await c.get(f"/v1/orders/{order['id']}", headers=t)).json()["invoice_number"]


async def test_split_bill_needs_module(api: Api) -> None:
    c = api.client
    plan = {"pack": "pack2", "tier": "starter", "create_slots": False}
    await c.put(f"/v1/platform/venues/{api.venue_id}/plan", headers=await platform_headers(api), json=plan)
    t = await till(api)
    order = (await c.post("/v1/orders", headers=t, json={"items": [api.line("Lime Juice")]})).json()
    r = await c.post(
        f"/v1/orders/{order['id']}/payments/cash", headers=t, json={"tendered": 10_000, "amount": 10_000}
    )
    assert r.json()["error"]["code"] == "module_not_in_plan"


async def test_tax_ledger_and_reconciliation(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    orders = []
    for item in ("Chicken Burger", "Lime Juice"):
        o = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line(item)]})).json()
        qr = (await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
        await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
        orders.append((o, qr))

    r = await c.get(api.av("/reports/tax-ledger.csv"), headers=api.admin)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2 and {"tax_SC", "tax_VAT"} <= set(rows[0])
    burger = next(x for x in rows if x["order_token"] == orders[0][0]["token"])
    assert burger["total"] == f"{orders[0][0]['total'] / 100:.2f}" and burger["paid_by"] == "lankaqr"

    summary = (await c.get(api.av("/reports/reconciliation"), headers=api.admin)).json()
    assert summary["by_method"]["lankaqr"]["net"] == sum(o["total"] for o, _ in orders)

    (o1, q1), (o2, q2) = orders
    bank = {
        "rows": [
            {"reference": q1["gateway_ref"], "amount": o1["total"]},
            {"reference": "BANK-EXTRA", "amount": 500},
        ]
    }
    m = (await c.post(api.av("/reports/reconciliation/match"), headers=api.admin, json=bank)).json()
    assert [x["reference"] for x in m["matched"]] == [q1["gateway_ref"]]
    assert [x["reference"] for x in m["missing_in_bank"]] == [q2["gateway_ref"]]
    assert m["unknown_in_bank"] == [{"reference": "BANK-EXTRA", "amount": 500}]
    assert m["all_clear"] is False
    bank = {
        "rows": [
            {"reference": q1["gateway_ref"], "amount": o1["total"] - 1},
            {"reference": q2["gateway_ref"], "amount": o2["total"]},
        ]
    }
    m = (await c.post(api.av("/reports/reconciliation/match"), headers=api.admin, json=bank)).json()
    assert len(m["amount_mismatch"]) == 1 and not m["missing_in_bank"]


async def test_operations_report(api: Api) -> None:
    c = api.client
    t = await till(api)
    manager = await api.login(await api.device("Till 2", "cashier"), "Kamala", "9999")
    await c.post(
        "/v1/shifts/open", headers=manager, json={"opening_float": 100_000}
    )  # cash refunds need a shift
    kds = await api.device("Kitchen", "kds")
    table = await api.device("Table 1", "table", table_ref="T1")
    a = (await c.post("/v1/orders", headers=t, json={"items": [api.line("Chicken Burger")]})).json()
    await c.post(f"/v1/orders/{a['id']}/payments/cash", headers=t, json={"tendered": a["total"]})
    await c.post(f"/v1/kds/orders/{a['id']}/bump", headers=kds)
    await c.post(
        f"/v1/kds/orders/{a['id']}/items/{a['items'][0]['id']}/remake", headers=kds, json={"reason": "burnt"}
    )
    await c.post(f"/v1/orders/{a['id']}/void", headers=manager, json={"reason": "Guest left"})
    b = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{b['id']}/cancel", headers=table, json={"reason": "changed mind"})
    call = (await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})).json()
    await c.post(f"/v1/service-requests/{call['id']}/ack", headers=t)

    ops = (await c.get(api.av("/reports/operations"), headers=api.admin)).json()
    assert ops["remakes"] == {"count": 1, "by_reason": {"burnt": 1}}
    assert ops["voids"]["count"] == 1 and ops["voids"]["reasons"] == {"Guest left": 1}
    assert ops["refunds"]["count"] == 1
    assert ops["completion_by_channel"]["table"] == {"started": 1, "paid": 0, "cancelled_or_expired": 1}
    assert ops["guest_calls"]["count"] == 1 and ops["guest_calls"]["answered"] == 1


async def test_receipt_shows_vat_number(api: Api) -> None:
    c = api.client
    await api.venue_settings(vat_number="123456789-7000", legal_name="Demo Hospitality (Pvt) Ltd")
    t = await till(api)
    o = (await c.post("/v1/orders", headers=t, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=t, json={"tendered": o["total"]})
    receipts = printed_receipts()
    assert receipts, "a receipt was printed"
    data = receipts[-1]
    assert b"VAT Reg. No: 123456789-7000" in data and b"Tax invoice" in data
