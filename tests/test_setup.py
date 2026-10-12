"""Install-time setup: payment methods and merchant details, card reader tests, printers with the
cloud print queue (Star CloudPRNT and screen-attached USB printers), and the go-live checklist."""

import base64
from typing import Any

import pytest

from kiosk.realtime.hub import hub
from tests.conftest import Api
from tests.test_card_terminal import configure


async def device_id(api: Api, name: str) -> str:
    devices = (await api.client.get(api.av("/devices"), headers=api.installer)).json()
    return str(next(d for d in devices if d["name"] == name)["id"])


async def cash_order(api: Api, t: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    c = api.client
    o = (await c.post("/v1/orders", headers=t, json={"items": items})).json()
    r = await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=t, json={"tendered": o["total"]})
    assert r.status_code == 201, r.text
    return r.json()["order"]


async def till(api: Api) -> dict[str, str]:
    t = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 0})
    return t


async def test_payment_methods_and_merchant_details(api: Api) -> None:
    c = api.client
    setup = (await c.get(api.av("/payment-setup"), headers=api.installer)).json()
    assert setup["methods"] == {"cash": True, "lankaqr": True, "card": True}
    assert setup["lankaqr"]["status"] == "not_set" and setup["providers"][0]["code"] == "mock"

    r = await c.put(
        api.av("/payment-setup/lankaqr"),
        headers=api.installer,
        json={"provider": "mock", "merchant_id": "M-1001", "secret": "sk_test_abcd1234"},
    )
    assert r.json()["secret_hint"] == "1234" and r.json()["status"] == "not_tested"
    assert "sk_test" not in r.text, "the key never comes back"
    assert (await c.post(api.av("/payment-setup/lankaqr/test"), headers=api.installer)).json()[
        "status"
    ] == "ok"
    # Changing the key means testing again; a wrong key shows why it failed.
    await c.put(
        api.av("/payment-setup/lankaqr"),
        headers=api.installer,
        json={"provider": "mock", "merchant_id": "M-1001", "secret": "wrong-key"},
    )
    failed = (await c.post(api.av("/payment-setup/lankaqr/test"), headers=api.installer)).json()
    assert failed["status"] == "failed" and "refused" in failed["last_error"]
    r = await c.put(api.av("/payment-setup/lankaqr"), headers=api.installer, json={"provider": "paypal"})
    assert r.json()["error"]["code"] == "bad_provider"

    # Switch LankaQR off: screens hide it and the server refuses it.
    r = await c.put(
        api.av("/payment-setup/methods"),
        headers=api.installer,
        json={"cash": True, "lankaqr": False, "card": True},
    )
    assert r.json()["methods"]["lankaqr"] is False
    kiosk = await api.device("Kiosk 1", "kiosk")
    assert (await c.get("/v1/devices/me", headers=kiosk)).json()["payments"]["lankaqr"] is False
    o = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    r = await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk)
    assert r.json()["error"]["code"] == "payment_method_off"
    r = await c.put(
        api.av("/payment-setup/methods"),
        headers=api.installer,
        json={"cash": False, "lankaqr": False, "card": False},
    )
    assert r.json()["error"]["code"] == "bad_setting"


async def test_card_reader_test(api: Api) -> None:
    c = api.client
    await api.device("Kiosk 1", "kiosk")
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="PAX-IM30-001")
    kiosk = await device_id(api, "Kiosk 1")
    r = (await c.post(api.av(f"/devices/{kiosk}/card-test"), headers=api.installer)).json()
    assert r["ok"] is True
    screens = (await c.get(api.av("/payment-setup"), headers=api.installer)).json()["card_screens"]
    assert screens[0]["tested_at"] and screens[0]["terminal_id"] == "PAX-IM30-001"
    await configure(api, "Kiosk 1", card_mode="reader", card_terminal_id="OFFLINE-9")
    r = (await c.post(api.av(f"/devices/{kiosk}/card-test"), headers=api.installer)).json()
    assert r["ok"] is False and "not online" in r["error"]


async def test_cloud_printer_gets_receipts_by_cloudprnt(api: Api) -> None:
    c = api.client
    p = (
        await c.post(
            api.av("/printers"),
            headers=api.installer,
            json={
                "name": "Counter printer",
                "connection": "cloud",
                "roles": ["receipt", "token"],
                "cash_drawer": True,
            },
        )
    ).json()
    url = p["cloud_path"]
    assert url.startswith("/v1/cloudprnt/") and p["online"] is False and p["tested"] is False
    assert (await c.post(url, json={"statusCode": "200 OK", "printerMAC": "00:11:62:aa"})).json() == {
        "jobReady": False
    }
    assert (await c.post("/v1/cloudprnt/not-a-token", json={})).status_code == 404

    # Test page: the printer polls, fetches it as text, confirms, and the printer is ticked.
    await c.post(api.av(f"/printers/{p['id']}/test"), headers=api.installer)
    poll = (await c.post(url, json={"statusCode": "200 OK"})).json()
    assert poll["jobReady"] and poll["mediaTypes"] == ["text/plain"]
    page = await c.get(url, params={"type": "text/plain", "token": poll["jobToken"]})
    assert "TEST PRINT" in page.text and "Counter printer" in page.text
    await c.delete(url, params={"code": "200 OK", "token": poll["jobToken"]})
    printers = (await c.get(api.av("/printers"), headers=api.installer)).json()
    assert printers[0]["tested"] and printers[0]["online"] and printers[0]["queued"] == 0

    # A paid order's receipt goes to the queue, not to the server's own printer.
    order = await cash_order(api, await till(api), [api.line("Chicken Burger")])
    poll = (await c.post(url, json={})).json()
    receipt = (await c.get(url, params={"type": "text/plain", "token": poll["jobToken"]})).text
    assert "TOTAL LKR" in receipt and order["token"] in receipt
    await c.delete(url, params={"code": "520 Printer Error", "token": poll["jobToken"]})
    jobs = (await c.get(api.av(f"/printers/{p['id']}/jobs"), headers=api.installer)).json()
    assert jobs[0]["status"] == "failed" and jobs[0]["error"] == "520 Printer Error"


async def test_station_printer_on_a_kitchen_screen(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, list[str]]] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append((type_, topics))
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    c = api.client
    bar_screen = await api.device("Bar KDS", "kds", station="bar")
    bar_id = await device_id(api, "Bar KDS")
    r = await c.post(
        api.av("/printers"),
        headers=api.installer,
        json={
            "name": "Bar",
            "connection": "screen",
            "roles": ["kitchen"],
            "stations": ["bar"],
            "device_id": bar_id,
        },
    )
    assert r.status_code == 201, r.text
    assert ("device.command", [f"device:{bar_id}"]) in sent, "the screen is asked to connect the printer"
    kiosk = await api.device("Kiosk 1", "kiosk")
    await api.device("Table 1", "table", table_ref="T1")
    r = await c.post(
        api.av("/printers"),
        headers=api.installer,
        json={
            "name": "Nope",
            "connection": "screen",
            "roles": ["kitchen"],
            "device_id": await device_id(api, "Table 1"),
        },
    )
    assert r.json()["error"]["code"] == "bad_printer", "not on a table screen"
    assert (await c.get("/v1/print/printers", headers=bar_screen)).json()[0]["name"] == "Bar"

    await api.venue_settings(print_kitchen_backup=True)
    await cash_order(api, await till(api), [api.line("Lime Juice"), api.line("Chicken Burger")])
    await cash_order(api, await till(api), [api.line("Chicken Burger")])  # nothing for the bar
    assert any(t == "print.job" and topics == [f"device:{bar_id}"] for t, topics in sent)
    [job] = (await c.get("/v1/print/jobs", headers=bar_screen)).json()
    assert "Lime Juice" in job["text"] and "Burger" not in job["text"]
    assert base64.b64decode(job["escpos_b64"]).startswith(b"\x1b@")
    assert (await c.get(f"/v1/print/jobs/{job['id']}", headers=kiosk)).status_code == 404

    r = await c.post(
        f"/v1/print/jobs/{job['id']}/result", headers=bar_screen, json={"ok": False, "error": "paper out"}
    )
    assert r.json()["status"] == "failed" and ("print.failed", ["orders", "kds"]) in sent
    assert (await c.get("/v1/print/jobs", headers=bar_screen)).json() == []


async def test_go_live_checklist(api: Api) -> None:
    c = api.client
    check = (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()
    by = {i["key"]: i for i in check["items"]}
    assert by["menu"]["done"] and by["taxes"]["done"] and not check["ready"]
    assert not by["payments"]["done"] and "QR payment" in by["payments"]["detail"]
    assert not by["test_order"]["done"]

    await c.put(api.av("/payment-setup/lankaqr"), headers=api.installer, json={"merchant_id": "M-1"})
    await c.post(api.av("/payment-setup/lankaqr/test"), headers=api.installer)
    p = (
        await c.post(
            api.av("/printers"),
            headers=api.installer,
            json={"name": "Receipts", "connection": "file", "roles": ["receipt"]},
        )
    ).json()
    await cash_order(api, await till(api), [api.line("Lime Juice")])
    by = {
        i["key"]: i for i in (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()["items"]
    }
    assert by["payments"]["done"] and by["test_order"]["done"]
    assert not by["printers"]["done"] and "Receipts" in by["printers"]["detail"]
    await c.post(api.av(f"/printers/{p['id']}/test"), headers=api.installer)
    await c.post(api.av(f"/printers/{p['id']}/confirm"), headers=api.installer)
    by = {
        i["key"]: i for i in (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()["items"]
    }
    assert by["printers"]["done"]


async def test_only_the_installation_team_sets_up_screens(api: Api) -> None:
    c = api.client
    owner = api.admin  # the restaurant's own login
    r = await c.post(api.av("/devices"), headers=owner, json={"type": "kiosk", "name": "K"})
    assert r.status_code == 403 and "installation team" in r.json()["error"]["message"]
    for path in ("/printers", "/payment-setup", "/setup-checklist"):
        assert (await c.get(api.av(path), headers=owner)).status_code == 403, path
    # The owner still sees its screens and runs the restaurant.
    assert (await c.get(api.av("/devices"), headers=owner)).status_code == 200
    assert (await c.get(api.av("/reports/sales"), headers=owner)).status_code == 200
    # Our installers see every restaurant.
    venues = (await c.get("/v1/admin/venues", headers=api.installer)).json()
    assert any(v["id"] == api.venue_id and v["tenant_name"] for v in venues)


async def test_screen_stays_set_up_until_the_console_says_otherwise(api: Api) -> None:
    c = api.client
    table = await api.device("Table 5", "table", table_ref="T5")
    assert (await c.get("/v1/devices/me", headers=table)).status_code == 200
    await c.patch(
        api.av(f"/devices/{await device_id(api, 'Table 5')}"),
        headers=api.installer,
        json={"is_active": False},
    )
    r = await c.get("/v1/devices/me", headers=table)
    assert r.status_code == 401 and r.json()["error"]["code"] == "device_not_set_up"


async def test_kiosk_slips_print_on_the_kiosk_printer(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    kiosk_id = await device_id(api, "Kiosk 1")
    t = await till(api)
    shared = (
        await c.post(
            api.av("/printers"),
            headers=api.installer,
            json={"name": "Counter", "connection": "cloud", "roles": ["receipt", "token"]},
        )
    ).json()
    own = (
        await c.post(
            api.av("/printers"),
            headers=api.installer,
            json={
                "name": "Kiosk 1 printer",
                "connection": "screen",
                "roles": ["receipt", "token"],
                "device_id": kiosk_id,
            },
        )
    ).json()

    async def jobs(p: dict[str, Any]) -> list[str]:
        return [
            j["label"]
            for j in (await c.get(api.av(f"/printers/{p['id']}/jobs"), headers=api.installer)).json()
        ]

    # Paid on the kiosk: the receipt comes out of the kiosk, not at the counter.
    o = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    qr = (await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    assert await jobs(own) == [f"receipt-{o['token']}"] and await jobs(shared) == []
    # "Pay at the cashier": the kiosk prints the number slip, the till's payment prints at the counter.
    o2 = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    await c.post(f"/v1/orders/{o2['id']}/print/token", headers=kiosk)
    await c.post(f"/v1/orders/{o2['id']}/payments/cash", headers=t, json={"tendered": o2["total"]})
    assert f"token-{o2['token']}" in await jobs(own)
    assert await jobs(shared) == [f"receipt-{o2['token']}"]

    check = {
        i["key"]: i for i in (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()["items"]
    }
    assert not check["kiosks"]["done"] and "Kiosk 1" in check["kiosks"]["detail"]


async def test_equipment_planned_and_installed(api: Api) -> None:
    c = api.client
    await api.device("Till A", "cashier")
    await api.device("Kiosk A", "kiosk")
    kit = {e["item"]: e for e in (await c.get(api.av("/equipment"), headers=api.installer)).json()}
    assert kit["router"]["planned"] == 1 and kit["router"]["manual"]
    assert kit["kiosk_printer"]["planned"] >= 1 and kit["kiosk_printer"]["installed"] == 0
    assert kit["cash_drawer"]["required_because"] == ["Each cashier takes cash"]
    check = {
        i["key"]: i for i in (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()["items"]
    }
    assert not check["equipment"]["done"] and "router" in check["equipment"]["detail"].lower()

    r = await c.put(api.av("/equipment"), headers=api.installer, json={"item": "router", "count": 1})
    assert {e["item"]: e for e in r.json()}["router"]["installed"] == 1
    r = await c.put(api.av("/equipment"), headers=api.installer, json={"item": "receipt_printer", "count": 1})
    assert r.json()["error"]["code"] == "counted_automatically"
    await c.post(
        api.av("/printers"),
        headers=api.installer,
        json={"name": "Till A printer", "connection": "cloud", "roles": ["receipt"], "cash_drawer": True},
    )
    kit = {e["item"]: e for e in (await c.get(api.av("/equipment"), headers=api.installer)).json()}
    assert kit["receipt_printer"]["installed"] == 1 and kit["cash_drawer"]["installed"] == 1

    tenants = (await c.get("/v1/platform/tenants", headers=api.installer)).json()
    demo = next(v for t in tenants for v in t["venues"] if v["id"] == api.venue_id)
    assert demo["setup"]["total"] == 11 and not demo["setup"]["ready"]
