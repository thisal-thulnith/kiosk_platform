"""Texts to guests (ready, receipt link), and keys: wrong-code limits, the one-writer rule."""

import json
from pathlib import Path
from typing import Any

from kiosk.config import settings
from kiosk.services.sms import receipt_ref
from tests.conftest import Api


def texts() -> list[dict[str, Any]]:
    f = Path(settings.print_dir) / "sms.log"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


async def test_order_ready_text_and_receipt_link(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    kds = await api.device("Kitchen", "kds")
    o = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    qr = (await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    r = await c.post(f"/v1/orders/{o['id']}/notify", headers=kiosk, json={"phone": "077 123 4567"})
    assert r.json()["notify"] is True and "notify_phone" not in r.json(), "the number never goes to screens"
    assert r.json()["texts_now"] == 1, "paid already: the receipt link goes at once"
    [receipt] = texts()
    assert receipt["to"] == "+94771234567" and "/v1/receipts/" in receipt["text"]

    await c.post(f"/v1/kds/orders/{o['id']}/bump", headers=kds)
    ready = texts()[-1]
    assert f"order {o['token']} is ready" in ready["text"] and "counter" in ready["text"]
    await c.post(f"/v1/kds/orders/{o['id']}/bump", headers=kds)
    assert len(texts()) == 2, "never twice"

    page = await c.get(f"/v1/receipts/{receipt_ref(o['id'])}")
    assert page.status_code == 200 and "TOTAL LKR" in page.text and o["token"] in page.text
    assert (await c.get(f"/v1/receipts/{o['id']}.forged0000000000000")).status_code == 404

    other = await api.device("Kiosk 2", "kiosk")
    r = await c.post(f"/v1/orders/{o['id']}/notify", headers=other, json={"phone": "0771234567"})
    assert r.status_code == 403, "another guest screen can't add a number to this order"


async def test_texts_can_be_switched_off(api: Api) -> None:
    c = api.client
    await api.venue_settings(sms_ready=False, sms_receipt=False)
    kiosk = await api.device("Kiosk 1", "kiosk")
    o = (await c.post("/v1/orders", headers=kiosk, json={"items": [api.line("Lime Juice")]})).json()
    qr = (await c.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk)).json()["payment"]
    await c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded")
    r = await c.post(f"/v1/orders/{o['id']}/notify", headers=kiosk, json={"phone": "0771234567"})
    assert r.json()["texts_now"] == 0 and texts() == []


async def test_wrong_setup_codes_are_limited(api: Api) -> None:
    c = api.client
    for _ in range(10):
        assert (await c.post("/v1/devices/pair", json={"code": "000000"})).status_code == 400
    r = await c.post("/v1/devices/pair", json={"code": "000000"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"
    for _ in range(10):
        await c.post("/v1/admin/auth/login", json={"email": "x@y.lk", "password": "nope-nope-1"})
    r = await c.post("/v1/admin/auth/login", json={"email": "admin@demo.lk", "password": "admin12345"})
    assert r.status_code == 429, "even the right password waits after too many wrong ones"


async def test_disabled_screen_key_and_hybrid_network_info(api: Api) -> None:
    c = api.client
    table = await api.device("Table 1", "table", table_ref="T1")
    me = (await c.get("/v1/devices/me", headers=table)).json()
    assert me["network"]["mode"] == "cloud"
    r = await c.put(api.av("/network"), headers=api.installer, json={"mode": "hybrid"})
    assert r.json()["mode"] == "hybrid" and r.json()["hub"] is None and r.json()["in_charge"] == "cloud"
    assert (await c.put(api.av("/network"), headers=api.admin, json={"mode": "cloud"})).status_code == 403
    code = (await c.post(api.av("/hub/setup-code"), headers=api.installer)).json()["code"]
    assert len(code) == 8
    check = {
        i["key"]: i for i in (await c.get(api.av("/setup-checklist"), headers=api.installer)).json()["items"]
    }
    assert not check["network"]["done"]
