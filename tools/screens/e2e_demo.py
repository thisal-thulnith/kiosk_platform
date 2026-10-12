"""Browser checks for the public demo (DEMO_MODE): the /try page, and the table screen in the browser
through a whole visit in both restaurant styles. Runs its own server.

cd frontend && npm run build && cd ..
uv run python tools/screens/e2e_demo.py            # screenshots go to ./e2e-demo-shots
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
from cdp import Browser, Tab, start_server

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8772)
parser.add_argument("--out", default="e2e-demo-shots")
ARGS = parser.parse_args()
BASE = f"http://127.0.0.1:{ARGS.port}"
OUT = Path(ARGS.out)
OUT.mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="kiosk-demo-"))


def table_screen(
    browser: Browser, api: httpx.Client, ref: str, w: int = 1280, h: int = 800
) -> tuple[Tab, dict[str, str]]:
    """What a tap on "Table T1" at /try does: a fresh screen, its key stored, the screen opened."""
    r = api.post("/v1/demo/screen", json={"type": "table", "table_ref": ref}).json()
    slot = ref.lower()
    tab = browser.tab(f"{BASE}/try", f"table-{slot}", w, h)
    tab.wait_text("Try every screen", 15)
    key = f"kiosk:dev:table:{slot}"
    saved = json.dumps({"token": r["device_token"], "device": r["device"]})
    tab.js(f"localStorage.setItem({json.dumps(key)}, {json.dumps(saved)})")
    tab.send("Page.navigate", url=f"{BASE}/demo/table?slot={slot}")
    tab.wait("location.pathname === '/demo/table'", 15)
    return tab, {"X-Device-Token": r["device_token"]}


def staff_screen(api: httpx.Client, type_: str, name: str, pin: str) -> dict[str, str]:
    dev = api.post("/v1/demo/screen", json={"type": type_}).json()
    h = {"X-Device-Token": dev["device_token"]}
    who = next(s for s in api.get("/v1/staff", headers=h).json() if s["name"] == name)
    tok = api.post("/v1/staff/pin-login", headers=h, json={"staff_id": who["id"], "pin": pin}).json()
    return {**h, "Authorization": f"Bearer {tok['staff_token']}"}


def add_dish(tab: Tab, api: httpx.Client, headers: dict[str, str], name: str) -> None:
    menu: dict[str, Any] = api.get("/v1/menu", headers=headers).json()
    cat = next(c for c in menu["categories"] if any(i["name"]["en"] == name for i in c["items"]))
    tab.click(cat["name"]["en"], "nav button")
    tab.click(name, f"[data-item={json.dumps(name)}]")


def main() -> None:
    env = {
        "ENV": "dev",
        "APP_MODE": "cloud",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite+aiosqlite:///{WORK}/d.db",
        "PRINT_DIR": str(WORK / "prints"),
        "CLOUD_URL": "",
        "COMING_SOON": "",
    }
    srv = start_server(ARGS.port, env)
    browser = Browser(WORK / "chrome", 9351)
    try:
        api = httpx.Client(base_url=BASE)
        tr = browser.tab(f"{BASE}/", "try", 1366, 1000)
        tr.wait("location.pathname === '/try'", 15)
        tr.wait_text("Table T6", 15)
        tr.wait_text("PIN 3333")
        tr.shot(OUT, "1-try")
        print("try: / opens the demo page with every screen, PINs and logins")

        # --- sit-down restaurant: order, cooking, on its way, enjoy, ask for the bill, paid
        t1, th = table_screen(browser, api, "T1")
        t1.wait_text("Tap to order", 15)
        t1.shot(OUT, "2-table-welcome")
        t1.js("document.querySelector('button').click()")
        add_dish(t1, api, th, "Chicken Burger")
        add_dish(t1, api, th, "Lime Juice")
        t1.shot(OUT, "3-table-menu")
        t1.click("Review order")
        t1.click("Send to the kitchen")
        t1.wait_text("Cooking", 15)
        t1.shot(OUT, "4-table-cooking")
        order = next(
            o for o in api.get("/v1/orders?table_ref=T1", headers=th).json() if o["status"] == "in_kitchen"
        )
        kitchen = api.post("/v1/demo/screen", json={"type": "kds"}).json()
        api.post(
            f"/v1/kds/orders/{order['id']}/bump", headers={"X-Device-Token": kitchen["device_token"]}, json={}
        ).raise_for_status()
        t1.wait_text("On its way", 15)
        waiter = staff_screen(api, "waiter", "Priya", "3333")
        api.post(f"/v1/orders/{order['id']}/served", headers=waiter).raise_for_status()
        t1.wait_text("Enjoy your meal", 15)
        t1.shot(OUT, "5-table-enjoy")
        t1.click("Call waiter")
        t1.wait_text("Waiter called")
        t1.click("Ask for the bill")
        t1.click("Cash", "button")
        t1.wait_text("bringing the bill", 10)
        t1.shot(OUT, "6-table-bill-asked")
        due = api.get(f"/v1/orders/{order['id']}", headers=th).json()
        pay = api.post(
            f"/v1/orders/{order['id']}/payments/cash",
            headers={**waiter, "Idempotency-Key": "demo-pay-1"},
            json={"tendered": due["total"]},
        )
        assert pay.status_code == 201, pay.text
        t1.wait_text("Thank you!", 15)
        t1.shot(OUT, "7-table-thanks")
        print("table (sit-down): order -> cooking -> on its way -> enjoy -> bill (cash) -> thank you")

        # --- quick service: pay first by QR on the table, then cooking, then collect at the counter
        api.post("/v1/demo/style", json={"style": "quick"}).raise_for_status()
        t2, th2 = table_screen(browser, api, "T2", 900, 1200)
        t2.wait_text("Tap to order", 15)
        t2.js("document.querySelector('button').click()")
        add_dish(t2, api, th2, "Chicken Burger")
        t2.click("Review order")
        t2.click("Place order")
        t2.wait_text("Please pay to start cooking", 15)
        t2.shot(OUT, "8-table-pay-first")
        t2.click("Pay by QR here")
        t2.wait_text("Scan to pay", 10)
        t2.shot(OUT, "9-table-qr")
        t2.click("Simulate payment")  # the demo's pretend bank
        t2.wait("[...document.querySelectorAll('h1')].some(h => h.textContent === 'Cooking')", 20)
        listed = api.get("/v1/orders?table_ref=T2", headers=th2).json()
        o2 = next(o for o in listed if o["status"] == "in_kitchen")
        api.post(
            f"/v1/kds/orders/{o2['id']}/bump", headers={"X-Device-Token": kitchen["device_token"]}, json={}
        ).raise_for_status()
        t2.wait_text("Collect at the counter", 15)
        t2.shot(OUT, "10-table-collect")
        print("table (quick service): place -> pay by QR -> cooking -> collect at the counter")
        print("OK: demo checked")
    finally:
        browser.close()
        srv.terminate()
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
