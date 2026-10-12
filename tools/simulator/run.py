"""Simulate a lunch rush against a running edge server.

    uv run kiosk initdb && uv run kiosk seed && uv run kiosk serve
    uv run python tools/simulator/run.py --orders 60

Plays admin, a cashier till, a kiosk, table screens and a kitchen screen. Measures how long
an order takes to reach the kitchen over WebSocket (target: under 2 seconds).
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from typing import Any

import httpx
from websockets.asyncio.client import connect

ADMIN = {"email": "admin@demo.lk", "password": "admin12345"}


class Sim:
    def __init__(self, base: str) -> None:
        self.base = base
        self.c = httpx.AsyncClient(base_url=base, timeout=15)
        self.admin: dict[str, str] = {}
        self.venue = ""
        self.items: list[dict[str, Any]] = []
        self.sent_at: dict[str, float] = {}
        self.latencies: list[float] = []

    async def call(self, method: str, path: str, **kw: Any) -> Any:
        r = await self.c.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text}")
        return r.json()

    async def device(self, type_: str, name: str, **extra: str) -> dict[str, str]:
        d = await self.call(
            "POST",
            f"/v1/admin/venues/{self.venue}/devices",
            headers=self.admin,
            json={"type": type_, "name": name, **extra},
        )
        p = await self.call("POST", "/v1/devices/pair", json={"code": d["pairing_code"]})
        return {"X-Device-Token": p["device_token"]}

    def cart(self) -> dict[str, Any]:
        lines = []
        for item in random.sample(self.items, k=random.randint(1, 3)):
            mods = [
                g["modifiers"][random.randrange(len(g["modifiers"]))]["id"]
                for g in item["modifier_groups"]
                if g["min_select"] >= 1
            ]
            lines.append({"menu_item_id": item["id"], "quantity": random.randint(1, 2), "modifier_ids": mods})
        return {"items": lines}

    async def watch_kitchen(self, kds_token: str, stop: asyncio.Event) -> None:
        ws_url = self.base.replace("http", "ws", 1) + f"/v1/ws?token={kds_token}"
        async with connect(ws_url) as ws:
            while not stop.is_set():
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
                except TimeoutError:
                    continue
                if msg.get("type") == "order.released":
                    oid = msg["data"]["order"]["id"]
                    if oid in self.sent_at:
                        self.latencies.append(time.perf_counter() - self.sent_at.pop(oid))

    async def run(self, venue: str, n: int) -> None:
        tok = await self.call("POST", "/v1/admin/auth/login", json=ADMIN)
        self.admin = {"Authorization": f"Bearer {tok['access_token']}"}
        self.venue = venue
        await self.call(
            "PATCH", f"/v1/admin/venues/{venue}", headers=self.admin, json={"settings": {"release_rule": "A"}}
        )
        staff = await self.call("GET", f"/v1/admin/venues/{venue}/staff", headers=self.admin)
        nimal = next(s for s in staff if s["name"] == "Nimal")

        till_dev = await self.device("cashier", "Sim till")
        login = await self.call(
            "POST", "/v1/staff/pin-login", headers=till_dev, json={"staff_id": nimal["id"], "pin": "1111"}
        )
        till = {**till_dev, "Authorization": f"Bearer {login['staff_token']}"}
        kiosk = await self.device("kiosk", "Sim kiosk")
        tables = [await self.device("table", f"Sim T{i}", table_ref=str(i)) for i in range(1, 4)]
        kds = await self.device("kds", "Sim expo")

        menu = await self.call("GET", "/v1/menu", headers=kiosk)
        self.items = [i for cat in menu["categories"] for i in cat["items"] if i["is_available"]]
        try:
            await self.call("POST", "/v1/shifts/open", headers=till, json={"opening_float": 1_000_000})
        except RuntimeError as exc:
            if "shift_open" not in str(exc):
                raise

        stop = asyncio.Event()
        watcher = asyncio.create_task(self.watch_kitchen(kds["X-Device-Token"], stop))
        await asyncio.sleep(0.3)

        t0 = time.perf_counter()
        paid = {"cash": 0, "lankaqr": 0, "card": 0}
        ids: list[str] = []
        for _ in range(n):
            channel = random.choice(["till", "kiosk", "table"])
            headers = till if channel == "till" else kiosk if channel == "kiosk" else random.choice(tables)
            order = await self.call("POST", "/v1/orders", headers=headers, json=self.cart())
            ids.append(order["id"])
            method = "cash" if channel == "till" else random.choice(["lankaqr", "cash"])
            self.sent_at[order["id"]] = time.perf_counter()
            if method == "lankaqr":
                qr = await self.call("POST", f"/v1/orders/{order['id']}/payments/lankaqr", headers=headers)
                await self.call("POST", f"/v1/dev/mock-gateway/{qr['payment']['gateway_ref']}/succeeded")
            else:  # guest walks to the cashier, who scans the code and takes cash
                await self.call(
                    "POST",
                    f"/v1/orders/{order['id']}/payments/cash",
                    headers=till,
                    json={"tendered": order["total"] + random.choice([0, 5_000, 10_000])},
                )
            paid[method] += 1

        # Kitchen: bump everything, then hand over
        for oid in ids:
            await self.call("POST", f"/v1/kds/orders/{oid}/bump", headers=kds, json={})
            await self.call("POST", f"/v1/orders/{oid}/complete", headers=kds)
        elapsed = time.perf_counter() - t0
        await asyncio.sleep(0.5)
        stop.set()
        await watcher

        report = await self.call("GET", f"/v1/admin/venues/{venue}/reports/sales", headers=self.admin)
        lat = sorted(self.latencies)
        print(f"\nOrders: {n} in {elapsed:.1f}s   payments: {paid}")
        if lat:
            p95 = lat[max(0, int(len(lat) * 0.95) - 1)]
            print(
                f"Paid -> kitchen over WebSocket: median {statistics.median(lat) * 1000:.0f} ms, "
                f"p95 {p95 * 1000:.0f} ms, max {lat[-1] * 1000:.0f} ms (target < 2000 ms)"
            )
        print(
            f"Report today: {report['orders']} paid orders, gross LKR {report['gross_total'] / 100:,.2f}, "
            f"avg bill LKR {report['average_bill'] / 100:,.2f}"
        )
        print("Top items:", ", ".join(f"{t['name']} x{t['quantity']}" for t in report["top_items"][:5]))
        await self.c.aclose()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--venue", required=True, help="Venue id printed by `kiosk seed`")
    ap.add_argument("--orders", type=int, default=40)
    args = ap.parse_args()
    asyncio.run(Sim(args.base).run(args.venue, args.orders))


if __name__ == "__main__":
    main()
