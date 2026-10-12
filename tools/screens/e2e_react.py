"""Browser checks for the React screens (POS, waiter, kitchen, kiosk, status board). Runs its own server.

cd frontend && npm run build && cd ..
uv run python tools/screens/e2e_react.py            # screenshots go to ./e2e-react-shots

The table screen is the Android app (docs/TABLE_APP_API.md); here a table is driven through its API.
"""

import argparse
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from cdp import Browser, Tab, start_server

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8771)
parser.add_argument("--out", default="e2e-react-shots")
ARGS = parser.parse_args()
BASE = f"http://127.0.0.1:{ARGS.port}"
OUT = Path(ARGS.out)
OUT.mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="kiosk-react-"))


def installer(api: httpx.Client) -> tuple[dict[str, str], str]:
    tok = api.post(
        "/v1/platform/auth/login", json={"email": "platform@kiosk.lk", "password": "platform12345"}
    ).json()
    adm = {"Authorization": f"Bearer {tok['access_token']}"}
    venue = next(v for v in api.get("/v1/admin/venues", headers=adm).json() if v["code"] == "DEMO")["id"]
    return adm, venue


def code(api: httpx.Client, adm: dict[str, str], venue: str, type_: str, name: str, **extra: str) -> str:
    r = api.post(
        f"/v1/admin/venues/{venue}/devices", headers=adm, json={"type": type_, "name": name, **extra}
    )
    r.raise_for_status()
    return str(r.json()["pairing_code"])


def screen(browser: Browser, path: str, pair: str, name: str, w: int, h: int) -> Tab:
    slug = {"kds": "kitchen", "status": "board"}.get(path, path)
    tab = browser.tab(f"{BASE}/{slug}?slot={name}&pair={pair}", name, w, h)
    tab.wait("!document.location.search.includes('pair=')")
    return tab


def pin(tab: Tab, who: str, digits: str) -> None:
    tab.click(who)
    for k in digits:
        tab.click(k)
    tab.click("OK")


def item_id(api: httpx.Client, headers: dict[str, str], name: str) -> str:
    menu: dict[str, Any] = api.get("/v1/menu", headers=headers).json()
    return next(i["id"] for c in menu["categories"] for i in c["items"] if i["name"]["en"] == name)


def launcher_and_identity(api: httpx.Client, adm: dict[str, str], venue: str) -> None:
    """A new tablet (its own browser): the installer's QR opens the old start page, it sets itself up,
    and every later start opens its screen by itself. The Setup console sees which tablet it is."""
    tablet = Browser(WORK / "tablet", 9342)
    try:
        qr = code(api, adm, venue, "kds", "Kitchen 2")
        t = tablet.tab(f"{BASE}/screens/app.html?pair={qr}", "tablet", 1280, 800, android=True)
        t.wait("location.pathname === '/demo/kitchen'", 15)
        t.wait_text("Kitchen · Kitchen 2")
        t.send("Page.navigate", url=f"{BASE}/")  # the tablet restarts its app
        time.sleep(1)
        t.wait("location.pathname === '/demo/kitchen'", 15)
        t.send("Page.navigate", url=f"{BASE}/")  # or someone types the server address
        time.sleep(1)
        t.wait("location.pathname === '/demo/kitchen'", 15)
        t.wait_text("Live")
        dev = next(
            d
            for d in api.get(f"/v1/admin/venues/{venue}/devices", headers=adm).json()
            if d["name"] == "Kitchen 2"
        )
        client = dev["client"]
        assert client["install_id"] and client["os"].startswith("Android") and client["ip"], client
        assert dev["connected"] and dev["same_tablet_as"] == [], dev
        cmd = api.post(
            f"/v1/admin/venues/{venue}/devices/{dev['id']}/command", headers=adm, json={"command": "identify"}
        )
        assert cmd.status_code == 200, cmd.text
        t.wait("!!document.querySelector('[data-identify]')")
        t.shot(OUT, "0-identify")
        print(f"launcher: set up once, reopens by itself; tablet seen as {client['os']} {client['ip']}")

        # The way to sign a screen in now: the restaurant's address + the screen's code (QR or typed).
        made = api.post(
            f"/v1/admin/venues/{venue}/devices", headers=adm, json={"type": "waiter", "name": "Handheld 2"}
        )
        screen_code = made.json()["screen_code"]
        t.send("Page.navigate", url=f"{BASE}/demo?code={screen_code}")  # what the QR opens
        time.sleep(1)
        t.wait("location.pathname === '/demo/waiter'", 15)
        # Typed by hand on another tablet: it takes the screen over; the first tablet is signed out.
        other = Browser(WORK / "tablet2", 9343)
        try:
            o = other.tab(f"{BASE}/demo", "tablet2", 820, 1180, android=True)
            o.wait("!!document.querySelector('input[name=code]')", 15)
            fill(o, "input[name=code]", screen_code.replace("-", "").lower())
            o.click("Sign in")
            o.wait("location.pathname === '/demo/waiter'", 15)
        finally:
            other.close()
        t.send("Page.navigate", url=f"{BASE}/demo/waiter")
        time.sleep(1)
        t.wait("!!document.querySelector('input[name=code]')", 15)  # signed out: asks for the code again
        print("sign-in: restaurant address + screen code (QR or typed); a second tablet signs the first out")
    finally:
        tablet.close()


def fill(tab: Tab, selector: str, value: str) -> None:
    """Type into a React input (sets the value the way a keyboard does, so React sees it)."""
    ok = tab.js(
        f"(() => {{ const el = document.querySelector({selector!r}); if (!el) return false;"
        " const set = Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set;"
        f" set.call(el, {value!r}); el.dispatchEvent(new Event('input', {{bubbles: true}}));"
        " return true; })()"
    )
    assert ok, f"{tab.name}: no {selector}"


def consoles(browser: Browser, api: httpx.Client, adm: dict[str, str], venue: str) -> None:
    """Platform console -> the restaurant's Setup console (screens with their tablets) -> Menu editor."""
    plat = browser.tab(f"{BASE}/platform", "platform", 1366, 1000)
    plat.click("Log in")
    plat.wait_text("Demo Café Colombo", 15)
    plat.shot(OUT, "14-platform")
    plat.js(
        "[...document.querySelectorAll('a,button')].find(a => a.textContent.includes('Open setup console')"
        " && a.closest('.card')?.textContent.includes('Demo Café')).click()"
    )
    plat.wait("location.pathname === '/demo/setup'", 15)
    plat.wait("!!document.querySelector('.step-pill')", 15)
    plat.click("Screens", "button.step-pill")
    plat.wait_text("Kitchen 2", 15)
    plat.wait_text("Android 14")  # which tablet each screen is on
    plat.wait_text("Identify")
    plat.shot(OUT, "15-setup-screens")
    plat.click("Restaurant", "button.step-pill")
    time.sleep(1.5)
    plat.shot(OUT, "15a-setup-restaurant")
    plat.click("Go live", "button.step-pill")
    time.sleep(1.5)
    plat.shot(OUT, "17-setup-go-live")
    print("consoles: platform -> setup console; screens show their tablets (Android 14), Identify")

    ed = browser.tab(f"{BASE}/demo/menu?as=installer", "menu", 1366, 1000)
    ed.click("Log in")  # logins are kept per browser tab
    ed.wait("!!document.querySelector('.cat-row')", 15)
    ed.click("Drinks", ".cat-row")
    ed.click("Lime Juice", ".tile")
    ed.wait("!!document.querySelector(\"input[aria-label='Price Rs']\")")
    fill(ed, "input[aria-label='Price Rs']", "375")
    ed.click("Save item")
    ed.wait_text("Every screen shows the change now")
    ed.shot(OUT, "16-menu-editor")
    kiosk = api.post("/v1/devices/pair", json={"code": code(api, adm, venue, "kiosk", "Kiosk 9")}).json()
    menu = api.get("/v1/menu", headers={"X-Device-Token": kiosk["device_token"]}).json()
    price = next(
        i["price"] for c in menu["categories"] for i in c["items"] if i["name"]["en"] == "Lime Juice"
    )
    assert price == 37500, price
    print("menu editor: price changed to Rs 375 and every screen gets it")


def main() -> None:
    env = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{WORK}/r.db",
        "PRINT_DIR": str(WORK / "prints"),
        "CLOUD_URL": "",
        "COMING_SOON": "",
    }
    srv = start_server(ARGS.port, env)
    browser = Browser(WORK / "chrome", 9341)
    try:
        api = httpx.Client(base_url=BASE)
        adm, venue = installer(api)
        api.patch(
            f"/v1/admin/venues/{venue}",
            headers=adm,
            json={"settings": {"dine_in_mode": "tab", "serve_mode": "waiter"}},
        ).raise_for_status()

        # --- every screen opens from the installer's link (one code) and stays set up
        pos = screen(browser, "pos", code(api, adm, venue, "cashier", "POS 1"), "pos", 1440, 900)
        pin(pos, "Nimal", "1111")
        pos.wait_text("Open cash shift")
        pos.click("Open shift")
        pos.wait_text("Takeaway")
        waiter = screen(browser, "waiter", code(api, adm, venue, "waiter", "Handheld 1"), "waiter", 420, 860)
        pin(waiter, "Priya", "3333")
        waiter.wait_text("Tables")
        kds = screen(browser, "kds", code(api, adm, venue, "kds", "Kitchen"), "kds", 1280, 800)
        kds.wait_text("All clear")
        board = screen(browser, "status", code(api, adm, venue, "status", "Board"), "board", 1280, 720)
        board.wait_text("Ready for pickup")
        kiosk = screen(browser, "kiosk", code(api, adm, venue, "kiosk", "Kiosk 1"), "kiosk", 1080, 1600)
        kiosk.wait_text("Tap to order")
        kiosk.shot(OUT, "1-kiosk-welcome")
        for t in (pos, waiter, kds, board):
            t.wait_text("Live")
        print("setup: 5 screens set up from links, all live")
        launcher_and_identity(api, adm, venue)

        # --- kiosk: order, pay at the counter
        kiosk.click("English", "span[role=button]")
        kiosk.click("Drinks", "nav button")
        kiosk.click("Lime Juice", "button[data-item]")
        kiosk.wait_text("Review order")
        kiosk.shot(OUT, "2-kiosk-menu")
        kiosk.click("Review order")
        kiosk.wait_text("Total")
        kiosk.click("Confirm order")
        kiosk.wait_text("How would you like to pay?")
        kiosk.shot(OUT, "3-kiosk-pay")
        kiosk.click("Pay at the cashier")
        kiosk.wait("!!document.querySelector('[data-token]')")
        token = kiosk.js("document.querySelector('[data-token]').dataset.token")
        kiosk.shot(OUT, "4-kiosk-counter")
        print(f"kiosk: order {token}, pay at the counter")

        # --- POS: live toast and the order waiting for payment; take cash with change
        pos.wait_text(f"New order {token}")
        pos.click("Orders", "button")
        pos.wait_text("Waiting for payment")
        pos.js(
            "[...document.querySelectorAll('button')].find(b => b.textContent.startsWith('Take payment')"
            f" && b.closest('[data-order]')?.dataset.order === {token!r}).click()"
        )
        pos.click("Cash")
        pos.click("Rs 1,000")
        pos.wait_text("Change to give")
        pos.shot(OUT, "5-pos-cash")
        pos.click("Cash received")
        pos.wait_text("change")
        print("pos: kiosk order paid in cash, change shown")

        # --- kitchen: the ticket appears; tap to start, bump; board and kiosk follow
        kds.wait(f"!!document.querySelector('[data-token=\"{token}\"]')")
        kds.shot(OUT, "6-kds-ticket")
        kds.click("Lime Juice", f'[data-token="{token}"] button')
        kds.click("Bump", f'[data-token="{token}"] button')
        board.wait(
            "[...document.querySelectorAll('section')].find(s => s.textContent.includes('Ready for pickup'))"
            f".textContent.includes({token!r})",
            15,
        )
        board.shot(OUT, "7-board-ready")
        kiosk.wait_text("Tap to order", 45)  # the kiosk went back to the start (privacy)
        print("kds: bumped; status board shows it ready")

        # --- a table (the Android app) calls; the POS says Priya is going; the waiter sees it
        t5 = api.post(
            "/v1/devices/pair", json={"code": code(api, adm, venue, "table", "Table T5", table_ref="T5")}
        ).json()
        th = {"X-Device-Token": t5["device_token"]}
        api.post("/v1/service-requests", headers=th, json={"kind": "call_waiter"}).raise_for_status()
        pos.wait_text("Table T5: Calling staff")
        pos.click("Tables", "button")
        pos.wait("!!document.querySelector('[data-table]')")
        pos.shot(OUT, "8a-pos-tables")
        pos.click("Calls", "button")
        pos.click("Coming", "button")
        pos.wait_text("Who is going?")
        pos.shot(OUT, "8-pos-pick-waiter")
        pos.click("Priya", "button")
        pos.wait_text("Priya is coming")
        waiter.wait_text("Priya is coming")
        mine = api.get("/v1/service-requests?mine=true", headers=th).json()
        assert mine[0]["coming"]["name"] == "Priya", mine
        print("calls: POS picked Priya; waiter app and the table see 'Priya is coming'")

        # --- the table orders (pay after eating); the waiter takes the payment at the table
        line = {"menu_item_id": item_id(api, th, "Chicken Burger"), "quantity": 2}
        order = api.post(
            "/v1/orders", headers={**th, "Idempotency-Key": "t5-1"}, json={"items": [line]}
        ).json()
        assert order["is_tab"], order
        pos.wait_text(f"New order {order['token']} · Table T5")
        hand = api.post(
            "/v1/devices/pair", json={"code": code(api, adm, venue, "waiter", "Handheld API")}
        ).json()
        hh = {"X-Device-Token": hand["device_token"]}
        priya = next(x for x in api.get("/v1/staff", headers=hh).json() if x["name"] == "Priya")
        tok = api.post(
            "/v1/staff/pin-login", headers=hh, json={"staff_id": priya["id"], "pin": "3333"}
        ).json()
        waiter_api = {**hh, "Authorization": f"Bearer {tok['staff_token']}"}
        # The kitchen finishes it: the waiter's tasks say "Take food to T5"; Served.
        kitchen = api.post(
            "/v1/devices/pair", json={"code": code(api, adm, venue, "kds", "Kitchen B")}
        ).json()
        bump = api.post(
            f"/v1/kds/orders/{order['id']}/bump", headers={"X-Device-Token": kitchen["device_token"]}, json={}
        )
        assert bump.status_code == 200, bump.text
        waiter.click("Tasks", "button")
        waiter.wait_text("Take food to T5")
        waiter.shot(OUT, "9a-waiter-tasks-food-ready")
        waiter.click("Served", "button")
        waiter.wait("!document.body.innerText.includes('Take food to T5')")
        assert api.get(f"/v1/orders/{order['id']}", headers=th).json()["served_at"]
        # The guests rate it low: it is at the top of the waiter's tasks until someone has seen it.
        fb = api.post(
            "/v1/feedback",
            headers=th,
            json={"rating": 2, "tags": ["slow"], "comment": "Took long", "order_id": order["id"]},
        )
        assert fb.status_code == 201, fb.text
        waiter.wait_text("Took long")
        waiter.click("Seen", "button")
        print("visit: food ready -> 'Take food to T5' -> Served; low feedback on the waiter's tasks -> Seen")
        api.post("/v1/service-requests", headers=th, json={"kind": "request_bill", "order_id": order["id"]})
        waiter.wait_text("Wants the bill")
        waiter.click("Tables", "button")
        waiter.click("T5", "[data-table]")
        waiter.wait_text("Take payment")
        waiter.shot(OUT, "9-waiter-table-check")
        waiter.click("Take payment")
        waiter.click("Cash")
        waiter.click("Exact")
        waiter.click("Cash received")
        waiter.wait_text("Nothing to pay")
        waiter.wait("!document.body.innerText.includes('Wants the bill')")  # paid: the bill call is answered
        waiter.click("← Tables")
        # Paid: the visit is over and the table needs cleaning.
        waiter.click("Tasks", "button")
        waiter.wait_text("Clean T5")
        waiter.click("Cleaned", "button")
        waiter.wait("!document.body.innerText.includes('Clean T5')")
        tmap = {t["table_ref"]: t for t in api.get("/v1/tables", headers=waiter_api).json()}
        assert tmap["T5"]["state"] in ("free", "closed") and not tmap["T5"]["needs_cleaning"], tmap["T5"]
        print("visit: paid -> 'Clean T5' -> Cleaned -> the table is free")
        waiter.click("My payments", "button")
        waiter.wait_text("Taken today")
        waiter.wait_text(order["token"])
        waiter.shot(OUT, "10-waiter-my-payments")
        print("waiter: took the tab at the table; it is in 'My payments'")

        # --- the payments ledger (standard: who took it, how, when, which order)
        pos.click("Payments")
        pos.wait_text("Today's payments")
        pos.wait_text("Priya")
        pos.wait_text("Nimal")
        pos.shot(OUT, "11-pos-ledger")
        led = api.get(f"/v1/admin/venues/{venue}/reports/payments", headers=adm).json()
        by = {line["token"]: line["collected_by"] for line in led["lines"]}
        assert by[token] == "Nimal" and by[order["token"]] == "Priya", by
        csv = api.get(f"/v1/admin/venues/{venue}/reports/payments.csv", headers=adm)
        assert csv.status_code == 200 and "Priya" in csv.text
        print("ledger: every payment shows who took it, the way, and the order")

        # --- the owner app: who did what
        rep = api.get(f"/v1/admin/venues/{venue}/reports/staff", headers=adm).json()
        priya = next(p for p in rep["staff"] if p["name"] == "Priya")
        assert priya["calls"]["answered"] == 1 and priya["payments"]["amount"] == order["total"], priya
        owner = browser.tab(f"{BASE}/demo/owner", "owner", 1280, 900)
        owner.click("Log in")
        owner.wait_text("Sales by hour", 15)
        owner.shot(OUT, "12-owner-sales")
        owner.click("Staff", "nav button")
        owner.wait("!!document.querySelector('[data-staff=Priya]')")
        owner.js("document.querySelector('[data-staff=Priya] button').click()")
        owner.wait_text("Calls answered")
        owner.shot(OUT, "13-owner-staff")
        owner.click("Tables", "nav button")
        owner.wait_text("Every table")
        owner.wait_text("T5")
        print("owner: sales, every person (orders, money, tables visited, answer time), every table")
        consoles(browser, api, adm, venue)
        time.sleep(0.2)
        print("OK: React screens checked")
    finally:
        browser.close()
        srv.terminate()
        shutil.rmtree(WORK, ignore_errors=True)  # Chrome profiles are big


if __name__ == "__main__":
    main()
