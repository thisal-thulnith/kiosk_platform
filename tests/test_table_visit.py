"""A table's visit, the way a restaurant works: cooking -> food ready (a waiter takes it) -> eating ->
feedback (staff see it) -> paid -> needs cleaning -> cleaned -> free."""

from typing import Any

from tests.conftest import Api


async def test_table_visit_from_cooking_to_clean(api: Api) -> None:
    c = api.client
    await api.venue_settings(dine_in_mode="tab", serve_mode="waiter")
    table = await api.device("Table T7", "table", table_ref="T7")
    waiter = await api.login(await api.device("Waiter 1", "waiter"), "Priya", "3333")
    kds = await api.device("Kitchen", "kds")

    async def t7() -> dict[str, Any]:
        tmap = {t["table_ref"]: t for t in (await c.get("/v1/tables", headers=waiter)).json()}
        return tmap["T7"]

    order = (await c.post("/v1/orders", headers=table, json={"items": [api.line("Lime Juice")]})).json()
    t = await t7()
    assert t["state"] == "cooking" and t["occupied_since"], t

    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds, json={})
    t = await t7()
    assert t["state"] == "ready" and t["to_serve"] == [{"id": order["id"], "token": order["token"]}]

    assert (await c.post(f"/v1/orders/{order['id']}/served", headers=waiter)).status_code == 200
    t = await t7()
    assert t["state"] == "eating" and t["to_serve"] == []

    r = await c.post(
        "/v1/feedback",
        headers=table,
        json={"rating": 2, "tags": ["slow"], "comment": "Took long", "order_id": order["id"]},
    )
    assert r.status_code == 201 and r.json()["low"] and r.json()["table_ref"] == "T7", r.text
    assert (await c.post("/v1/feedback", headers=table, json={"rating": 9})).status_code == 422
    assert (
        await c.post("/v1/feedback", headers=table, json={"rating": 4, "tags": ["meh"]})
    ).status_code == 400
    t = await t7()
    assert t["feedback"]["rating"] == 2 and t["feedback"]["comment"] == "Took long"
    seen = (await c.get("/v1/feedback", headers=waiter)).json()
    assert seen[0]["low"] and not seen[0]["seen"]
    r = await c.post(f"/v1/feedback/{seen[0]['id']}/seen", headers=waiter)
    assert r.json()["seen"] and r.json()["seen_by"] == "Priya"
    assert (await c.get("/v1/feedback", headers=table)).status_code == 403, "guests don't read feedback"

    await c.post(
        "/v1/service-requests", headers=table, json={"kind": "call_waiter"}
    )  # still open when paying
    r = await c.post(
        f"/v1/orders/{order['id']}/payments/cash", headers=waiter, json={"tendered": order["total"]}
    )
    assert r.status_code == 201, r.text
    t = await t7()
    assert t["state"] == "cleaning" and t["needs_cleaning"] and not t["occupied_since"], t
    assert t["requests"] == [], "the visit is over: its calls are answered"

    assert (await c.post("/v1/tables/T7/cleaned", headers=waiter)).status_code == 200
    t = await t7()
    assert t["state"] == "free" and not t["needs_cleaning"]

    rep = (await c.get(api.av("/reports/feedback"), headers=api.admin)).json()
    assert rep["count"] == 1 and rep["average"] == 2 and rep["low"] == 1 and rep["tags"] == {"slow": 1}
    assert rep["by_waiter"] == {"Priya": {"count": 1, "average": 2}}
    assert rep["comments"][0]["comment"] == "Took long"
