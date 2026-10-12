"""Kitchen flow: priority, promised times, hold and fire, remakes, congestion score."""

from datetime import datetime

from kiosk.domain.orders import congestion, estimate_minutes
from tests.conftest import Api


async def paid_order(api: Api, headers: dict[str, str], item: str = "Chicken Burger", **line: object) -> dict:
    c = api.client
    order = (await c.post("/v1/orders", headers=headers, json={"items": [{**api.line(item), **line}]})).json()
    r = await c.post(
        f"/v1/orders/{order['id']}/payments/cash", headers=headers, json={"tendered": order["total"]}
    )
    assert r.status_code == 201, r.text
    return r.json()["order"]


async def cashier(api: Api) -> dict[str, str]:
    till = await api.login(await api.device("Till 1", "cashier"), "Nimal", "1111")
    await api.client.post("/v1/shifts/open", headers=till, json={"opening_float": 0})
    return till


def test_estimate_and_congestion_rules() -> None:
    assert estimate_minutes([8, 12], open_before=0, cooks=3) == 12
    assert estimate_minutes([8], open_before=6, cooks=3) == 12, (
        "2 extra minutes per full round of orders ahead"
    )
    assert congestion(6, 600, 3, 8, 12) == {"score_minutes": 20.0, "level": "overloaded"}
    assert congestion(1, 300, 3, 8, 12)["level"] == "normal"


async def test_rush_goes_first_and_promised_time_is_set(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    kds = await api.device("Kitchen", "kds")
    first = await paid_order(api, till)
    second = await paid_order(api, till, "Lime Juice")
    assert first["promised_at"] and datetime.fromisoformat(first["promised_at"]) > datetime.fromisoformat(
        first["released_at"]
    )
    tokens = [t["token"] for t in (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"]]
    assert tokens == [first["token"], second["token"]]

    r = await c.post(f"/v1/orders/{second['id']}/priority", headers=till, json={"priority": "rush"})
    assert r.json()["priority"] == "rush"
    tickets = (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"]
    assert [t["token"] for t in tickets] == [second["token"], first["token"]]
    assert tickets[0]["priority"] == "rush"
    # Guests and kitchen screens can't change priority.
    assert (
        await c.post(f"/v1/orders/{first['id']}/priority", headers=kds, json={"priority": "vip"})
    ).status_code == 401


async def test_hold_and_fire_course_timing(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    kds = await api.device("Kitchen", "kds")
    cart = {"items": [api.line("French Fries"), {**api.line("Devilled Chicken"), "hold": True}]}
    order = (await c.post("/v1/orders", headers=till, json=cart)).json()
    assert [i["kds_status"] for i in order["items"]] == ["queued", "held"]
    await c.post(f"/v1/orders/{order['id']}/payments/cash", headers=till, json={"tendered": order["total"]})

    ticket = (await c.get("/v1/kds/tickets", headers=kds)).json()["tickets"][0]
    assert ticket["held"] == 1
    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    after = (await c.get(f"/v1/orders/{order['id']}", headers=till)).json()
    assert after["status"] == "in_kitchen", "not ready while the main course is held"
    assert [i["kds_status"] for i in after["items"]] == ["done", "held"]

    fired = (await c.post(f"/v1/orders/{order['id']}/fire", headers=till)).json()
    assert [i["kds_status"] for i in fired["items"]] == ["done", "queued"]
    assert (await c.post(f"/v1/orders/{order['id']}/fire", headers=till)).json()["error"][
        "code"
    ] == "nothing_held"
    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    assert (await c.get(f"/v1/orders/{order['id']}", headers=till)).json()["status"] == "ready"

    # Guests cannot hold items.
    table = await api.device("Table 1", "table", table_ref="T1")
    r = await c.post("/v1/orders", headers=table, json={"items": [{**api.line("Lime Juice"), "hold": True}]})
    assert r.json()["error"]["code"] == "hold_staff_only"


async def test_remake_with_reason(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    kds = await api.device("Kitchen", "kds")
    order = await paid_order(api, till)
    item = order["items"][0]
    r = await c.post(
        f"/v1/kds/orders/{order['id']}/items/{item['id']}/remake", headers=kds, json={"reason": "burnt"}
    )
    assert r.json()["error"]["code"] == "bad_item_state", "only finished items can be remade"
    await c.post(f"/v1/kds/orders/{order['id']}/bump", headers=kds)
    assert (await c.get(f"/v1/orders/{order['id']}", headers=till)).json()["status"] == "ready"

    r = await c.post(
        f"/v1/kds/orders/{order['id']}/items/{item['id']}/remake", headers=kds, json={"reason": "tasty"}
    )
    assert r.json()["error"]["code"] == "bad_reason"
    r = await c.post(
        f"/v1/kds/orders/{order['id']}/items/{item['id']}/remake", headers=kds, json={"reason": "dropped"}
    )
    again = r.json()
    assert again["status"] == "in_kitchen" and again["items"][0]["kds_status"] == "queued"
    assert again["items"][0]["remake_count"] == 1


async def test_kitchen_load(api: Api) -> None:
    c = api.client
    till = await cashier(api)
    kds = await api.device("Kitchen", "kds")
    for _ in range(3):
        await paid_order(api, till)
    load = (await c.get("/v1/kds/load", headers=kds)).json()
    assert load["open_tickets"] == 3 and load["cooks"] == 3
    assert load["level"] in {"normal", "busy", "overloaded"}
    owner = (await c.get(api.av("/reports/kitchen-load"), headers=api.admin)).json()
    assert owner["open_tickets"] == 3
