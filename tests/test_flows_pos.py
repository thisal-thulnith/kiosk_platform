"""Service flows (choose how the restaurant works, required parts come with it), all-in-one hardware,
and the restaurant's own POS: signed order events out, payment and menu in."""

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest

from kiosk.domain.modules import PlanError, build_plan
from kiosk.services import posbridge
from tests.conftest import Api
from tests.test_setup import device_id
from tests.test_tenancy import NEW, platform_headers


def test_flows_bring_what_they_need() -> None:
    plan = build_plan("custom", modules=["R-CORE", "R-KDS"], flows=["kiosk_self_order"])
    assert plan["screens"] == {"kds": 1, "kiosk": 1}, "no status board unless chosen"
    assert {"R-SELF", "R-PAY"} <= set(plan["modules"])
    plan2 = build_plan(
        "custom", modules=["R-CORE", "R-KDS"], flows=["kiosk_self_order", "status_display", "table_lock"]
    )
    assert plan2["screens"]["status"] == 1 and plan2["flows"][:2] == ["kiosk_self_order", "table_order"]
    assert plan2["settings"]["table_access"] == "staff_opens"
    assert plan["hardware"]["kiosk_printer"] == 1 and plan["hardware"]["router"] == 1
    assert plan["settings"] == {"release_rule": "A", "serve_mode": "self_pickup"}

    plan = build_plan("custom", modules=["R-CORE", "R-KDS"], flows=["waiter_service"])
    assert plan["flows"] == ["table_order", "waiter_service"], "waiters need table ordering"
    assert plan["screens"]["cashier"] == 1, "tables need a cashier to pay at"
    assert plan["settings"]["serve_mode"] == "waiter"

    plan = build_plan("custom", modules=["R-CORE", "R-KDS"], flows=["table_order", "existing_pos"])
    assert "cashier" not in plan["screens"], "their own POS is the cashier"
    assert "R-BRIDGE" in plan["modules"]

    plan = build_plan("custom", modules=["R-CORE", "R-KDS"], flows=["offline_hybrid", "table_tab"])
    assert plan["hardware"]["hub"] == 1 and plan["hardware"]["ups"] == 1, "the hub needs a UPS"
    assert plan["settings"]["network_mode"] == "hybrid" and plan["settings"]["dine_in_mode"] == "tab"

    with pytest.raises(PlanError) as err:
        build_plan("pack1", "starter", flows=["table_order"])
    assert err.value.code == "not_an_addon"
    with pytest.raises(PlanError):
        build_plan("custom", modules=["R-CORE", "R-KDS"], flows=["teleport"])


async def test_new_restaurant_gets_flow_settings(api: Api) -> None:
    c = api.client
    body = {
        **NEW,
        "plan": {
            "pack": "custom",
            "modules": ["R-CORE", "R-KDS"],
            "flows": ["kiosk_self_order", "guest_sms"],
        },
    }
    r = await c.post("/v1/platform/tenants", headers=await platform_headers(api), json=body)
    assert r.status_code == 201, r.text
    venue = r.json()["venues"][0]
    v = (await c.get(f"/v1/admin/venues/{venue['id']}", headers=api.installer)).json()
    assert v["settings"]["release_rule"] == "A" and v["settings"]["sms_ready"] is True
    names = {
        d["name"]
        for d in (await c.get(f"/v1/admin/venues/{venue['id']}/devices", headers=api.installer)).json()
    }
    assert {"Kiosk 1", "Kitchen 1"} <= names, "slots from the flows"


async def test_all_in_one_kiosk_sets_up_its_built_ins(api: Api) -> None:
    c = api.client
    await api.device("Kiosk A", "kiosk")
    kid = await device_id(api, "Kiosk A")
    r = await c.put(api.av(f"/devices/{kid}/hardware"), headers=api.installer, json={"model": "all_in_one"})
    assert r.status_code == 200, r.text
    assert "Type the card reader's serial number" in r.json()["to_do"]
    r = await c.put(
        api.av(f"/devices/{kid}/hardware"),
        headers=api.installer,
        json={"model": "all_in_one", "card_terminal_id": "PAX-IM30-9"},
    )
    printers = (await c.get(api.av("/printers"), headers=api.installer)).json()
    [builtin] = [p for p in printers if p["device_id"] == kid]
    assert builtin["name"] == "Kiosk A built-in printer" and builtin["roles"] == ["receipt", "token"]
    dev = next(d for d in (await c.get(api.av("/devices"), headers=api.installer)).json() if d["id"] == kid)
    assert dev["card"] == {"mode": "reader", "terminal_id": "PAX-IM30-9"} and dev["hardware"]["scanner"]
    kit = {e["item"]: e for e in (await c.get(api.av("/equipment"), headers=api.installer)).json()}
    assert kit["kiosk_printer"]["installed"] == 1 and kit["scanner"]["installed"] == 1
    r = await c.put(api.av(f"/devices/{kid}/hardware"), headers=api.installer, json={"model": "pos_terminal"})
    assert r.json()["error"]["code"] == "bad_model", "a POS terminal is not a kiosk"
    r = await c.put(api.av(f"/devices/{kid}/hardware"), headers=api.admin, json={"model": "tablet"})
    assert r.status_code == 403


class FakePos:
    def __init__(self, fail: int = 0) -> None:
        self.got: list[httpx.Request] = []
        self.fail = fail

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.got.append(request)
        if self.fail:
            self.fail -= 1
            return httpx.Response(503, text="POS busy")
        return httpx.Response(200, json={"ok": True})


async def test_existing_pos_gets_signed_events_and_pays(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    pos = FakePos(fail=1)
    monkeypatch.setattr(posbridge, "TRANSPORT", httpx.MockTransport(pos))
    r = await c.put(
        api.av("/pos"),
        headers=api.installer,
        json={"pos_name": "Tillpoint", "url": "https://pos.example.lk/hook", "secret": "s3cret"},
    )
    assert r.json()["connected"] and r.json()["has_secret"] and "order.paid" in r.json()["events"]
    test = (await c.post(api.av("/pos/test"), headers=api.installer)).json()
    assert test == {"ok": False, "response_code": 503, "error": "POS busy"}, "a busy POS is reported"
    assert (await c.post(api.av("/pos/test"), headers=api.installer)).json()["ok"]
    key = (await c.post(api.av("/pos/key"), headers=api.installer)).json()["key"]
    pk = {"X-Pos-Key": key}

    # Their menu comes in by PLU; prices follow the POS.
    lime = api.items["Lime Juice"]
    r = await c.put(
        "/v1/pos/menu",
        headers=pk,
        json={
            "items": [
                {"plu": "1001", "name": "Iced Milo", "price": 45000, "category": "Drinks"},
                {"plu": "1002", "name": "Egg Roti", "price": 30000, "category": "Short eats"},
            ]
        },
    )
    assert r.json() == {"added": 2, "updated": 0}
    r = await c.put(
        "/v1/pos/menu", headers=pk, json={"items": [{"plu": "1001", "name": "Iced Milo", "price": 50000}]}
    )
    assert r.json() == {"added": 0, "updated": 1}
    menu = (await c.get("/v1/pos/menu", headers=pk)).json()
    milo = next(i for cat in menu["categories"] for i in cat["items"] if i["external_code"] == "1001")
    assert milo["price"] == 50000

    # A kiosk "pay at the cashier" order reaches their POS, signed, with PLU codes.
    kiosk = await api.device("Kiosk 1", "kiosk")
    o = (
        await c.post(
            "/v1/orders",
            headers=kiosk,
            json={
                "items": [
                    {"menu_item_id": milo["id"], "quantity": 2, "modifier_ids": []},
                    {"menu_item_id": lime["id"], "quantity": 1, "modifier_ids": []},
                ]
            },
        )
    ).json()
    created = [q for q in pos.got if q.headers["X-Kiosk-Event"] == "order.created"][-1]
    assert hmac.compare_digest(
        created.headers["X-Kiosk-Signature"], hmac.new(b"s3cret", created.content, hashlib.sha256).hexdigest()
    )
    body: dict[str, Any] = json.loads(created.content)
    assert body["order"]["token"] == o["token"] and body["order"]["lines"][0]["plu"] == "1001"

    # The POS takes the money and tells us: kitchen starts, sent twice = recorded once.
    for _ in range(2):
        r = await c.post(
            f"/v1/pos/orders/{o['id']}/paid", headers=pk, json={"reference": "R-7781", "method": "card"}
        )
    paid = r.json()
    assert paid["payment_status"] == "paid" and paid["status"] == "in_kitchen"
    assert [p["method"] for p in paid["payments"]] == ["pos"]
    assert any(q.headers["X-Kiosk-Event"] == "order.paid" for q in pos.got)
    since = (await c.get("/v1/pos/orders", headers=pk)).json()
    assert any(x["id"] == o["id"] for x in since["orders"])
    assert (await c.get("/v1/pos/orders", headers={"X-Pos-Key": "pos_wrong"})).status_code == 401
    log = (await c.get(api.av("/pos/deliveries"), headers=api.installer)).json()
    assert {"order.created", "order.paid"} <= {d["event"] for d in log}
