"""Tables opened and closed by staff: an empty table can't order; the POS opens it for guests,
runs it (orders, calls, payment) and closes it when they leave."""

from typing import Any

import pytest

from kiosk.realtime.hub import hub
from tests.conftest import Api


async def pos(api: Api) -> dict[str, str]:
    t = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=t, json={"opening_float": 0})
    return t


async def test_staff_open_and_close_tables(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    real = hub.publish

    async def spy(venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Any:
        sent.append((type_, data))
        return await real(venue_id, type_, data, topics)

    monkeypatch.setattr(hub, "publish", spy)
    c = api.client
    await api.venue_settings(table_access="staff_opens")
    table = await api.device("Table T4", "table", table_ref="T4")
    me = (await c.get("/v1/devices/me", headers=table)).json()
    assert me["table"] == {"ref": "T4", "access": "staff_opens", "open": False}

    r = await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})
    assert r.json()["error"]["code"] == "table_closed", "an empty table can't order"
    # Guests can still call staff from a closed table.
    r = await c.post("/v1/service-requests", headers=table, json={"kind": "call_waiter"})
    assert r.status_code in (200, 201), r.text

    till = await pos(api)
    tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=till)).json()}
    assert tmap["T4"]["open"] is False and tmap["T4"]["state"] == "calling"
    assert (await c.post("/v1/tables/T4/open", headers=table)).status_code == 403, "staff only"
    assert (await c.post("/v1/tables/T4/open", headers=till)).json()["open"] is True
    assert ("table.state", {"table_ref": "T4", "open": True}) in sent, "the table screen unlocks live"

    o = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    assert o["table_ref"] == "T4"
    r = await c.post("/v1/tables/T4/close", headers=till)
    assert r.json()["error"]["code"] == "table_unpaid" and o["token"] in r.json()["error"]["message"]

    await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=till, json={"tendered": o["total"]})
    closed = (await c.post("/v1/tables/T4/close", headers=till)).json()
    assert closed["open"] is False and closed["calls_cleared"] == 0, "opening the table answered the call"
    assert any(t == "table.cleared" for t, _ in sent)
    assert (await c.get("/v1/devices/me", headers=table)).json()["table"]["open"] is False
    tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=till)).json()}
    assert tmap["T4"]["state"] in ("closed", "cooking")


async def test_staff_ordering_opens_the_table_and_paid_tab_closes_it(api: Api) -> None:
    c = api.client
    await api.venue_settings(table_access="staff_opens", dine_in_mode="tab")
    table = await api.device("Table T5", "table", table_ref="T5")
    waiter_here = await api.login(table, "Nimal", "1111")  # waiter assist on the table
    o = (await c.post("/v1/orders", headers=waiter_here, json={"items": [api.line("Lime Juice")]})).json()
    assert o["is_tab"] and (await c.get("/v1/devices/me", headers=table)).json()["table"]["open"] is True
    more = await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})
    assert more.status_code == 201, "guests order the next round themselves"
    till = await pos(api)
    tab = more.json()
    await c.post(f"/v1/orders/{tab['id']}/payments/cash", headers=till, json={"tendered": tab["total"]})
    assert (await c.get("/v1/devices/me", headers=table)).json()["table"]["open"] is False, (
        "paid tab: visit over"
    )


async def test_open_tables_by_default(api: Api) -> None:
    table = await api.device("Table T6", "table", table_ref="T6")
    me = (await api.client.get("/v1/devices/me", headers=table)).json()
    assert me["table"]["open"] is True and me["table"]["access"] == "open"
    r = await api.client.patch(api.av(), headers=api.admin, json={"settings": {"table_access": "sometimes"}})
    assert r.json()["error"]["code"] == "bad_setting"
