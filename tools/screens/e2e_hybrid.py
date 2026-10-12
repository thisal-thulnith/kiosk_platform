"""Hybrid (hub + cloud) end to end, with two real servers and a real browser.

  1. the installer connects a hub to the cloud with a one-time code
  2. screens are set up through the hub; the cloud sends them back to the hub while it's alive
  3. a LankaQR payment confirmed by the bank at the cloud is handed to the hub
  4. INTERNET DOWN (cloud stopped): the kiosk, cashier and kitchen keep working through the hub
  5. internet back: everything reaches the cloud, exactly once
  6. HUB DOWN: screens use the cloud (backup numbers from 500); the hub comes back and catches up
  7. the React kiosk in the browser switches Local -> Cloud -> Local by itself

uv run python tools/screens/e2e_hybrid.py
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from cdp import Browser, start_server

CLOUD, HUB = 8781, 8782
CLOUD_URL, HUB_URL = f"http://127.0.0.1:{CLOUD}", f"http://127.0.0.1:{HUB}"
WORK = Path(tempfile.mkdtemp(prefix="kiosk-hybrid-"))
OUT = Path("e2e-hybrid-shots")
OUT.mkdir(exist_ok=True)
CLOUD_ENV = {
    "APP_MODE": "cloud",
    "DATABASE_URL": f"sqlite+aiosqlite:///{WORK}/cloud.db",
    "PUBLIC_URL": CLOUD_URL,
    "PRINT_DIR": str(WORK / "cloud-prints"),
    "HUB_TIMEOUT_SECONDS": "6",
    "CLOUD_URL": "",
    "COMING_SOON": "",
}
HUB_ENV = {
    "APP_MODE": "edge",
    "DATABASE_URL": f"sqlite+aiosqlite:///{WORK}/hub.db",
    "HUB_FILE": str(WORK / "hub.json"),
    "LAN_URL": HUB_URL,
    "COMING_SOON": "",
    "PRINT_DIR": str(WORK / "hub-prints"),
    "SYNC_INTERVAL_SECONDS": "1",
}


def serve(port: int, env: dict[str, str]) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        ["uv", "run", "kiosk", "serve", "--host", "127.0.0.1", "--port", str(port)],
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/v1/health", timeout=1)
            return proc
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError(f"server on {port} did not start")


def stop(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    proc.wait(10)


def until(what: str, check: Any, timeout: float = 20) -> Any:
    end = time.time() + timeout
    while time.time() < end:
        try:
            value = check()
            if value:
                return value
        except httpx.HTTPError:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"timed out waiting for: {what}")


def main() -> None:
    cloud = start_server(CLOUD, CLOUD_ENV)
    hub = None
    browser = None
    try:
        c = httpx.Client(base_url=CLOUD_URL, timeout=10)
        tok = c.post(
            "/v1/platform/auth/login", json={"email": "platform@kiosk.lk", "password": "platform12345"}
        )
        inst = {"Authorization": f"Bearer {tok.json()['access_token']}"}
        venue = next(v for v in c.get("/v1/admin/venues", headers=inst).json() if v["code"] == "DEMO")["id"]
        base = f"/v1/admin/venues/{venue}"

        # 1. Connect the hub with a one-time code; the hub pulls the restaurant's config.
        code = c.post(f"{base}/hub/setup-code", headers=inst).json()["code"]
        full = {**os.environ, **HUB_ENV}
        subprocess.run(["uv", "run", "kiosk", "initdb"], env=full, check=True, capture_output=True)
        r = subprocess.run(
            ["uv", "run", "kiosk", "hub-setup", "--cloud", CLOUD_URL, "--code", code, "--lan-url", HUB_URL],
            env=full,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0 and "Hub connected to Demo" in r.stdout, r.stdout + r.stderr
        hub = serve(HUB, HUB_ENV)
        net = until(
            "hub online",
            lambda: (n := c.get(f"{base}/network", headers=inst).json())["in_charge"] == "hub" and n,
        )
        assert net["mode"] == "hybrid" and net["hub"]["lan_url"] == HUB_URL
        print("1. hub connected with one code; cloud says the hub is in charge")

        # 2. Screens: codes from the cloud console, typed on the hub (the hub asks the cloud).
        def screen(type_: str, name: str, **extra: str) -> dict[str, str]:
            d = c.post(f"{base}/devices", headers=inst, json={"type": type_, "name": name, **extra}).json()
            p = httpx.post(f"{HUB_URL}/v1/devices/pair", json={"code": d["pairing_code"]}, timeout=15)
            assert p.status_code == 200, p.text
            return {"X-Device-Token": p.json()["device_token"]}

        h = httpx.Client(base_url=HUB_URL, timeout=10)
        kiosk = screen("kiosk", "Kiosk H")
        kds = screen("kds", "Kitchen H")
        till = screen("cashier", "Till H")
        me = h.get("/v1/devices/me", headers=kiosk).json()
        assert me["network"] == {
            "mode": "hybrid",
            "hub_url": HUB_URL,
            "cloud_url": CLOUD_URL,
            "served_by": "hub",
        }
        r = c.get("/v1/menu", headers=kiosk)
        assert r.status_code == 409 and r.json()["error"]["code"] == "use_hub", "one writer: the hub"
        menu = h.get("/v1/menu", headers=kiosk).json()
        items = {i["name"]["en"]: i for cat in menu["categories"] for i in cat["items"]}
        line = {"menu_item_id": items["Lime Juice"]["id"], "quantity": 1, "modifier_ids": []}
        print("2. screens set up through the hub; the cloud sends them back to the hub")

        # 3. LankaQR on the hub; the bank's confirmation arrives at the cloud and is handed over.
        o = h.post("/v1/orders", headers=kiosk, json={"items": [line]}).json()
        qr = h.post(f"/v1/orders/{o['id']}/payments/lankaqr", headers=kiosk).json()["payment"]
        until(
            "cloud has the payment",
            lambda: c.post(f"/v1/dev/mock-gateway/{qr['gateway_ref']}/succeeded").status_code == 200,
        )
        until(
            "hub got the payment",
            lambda: h.get(f"/v1/orders/{o['id']}", headers=kiosk).json()["payment_status"] == "paid",
        )
        assert h.get(f"/v1/orders/{o['id']}", headers=kiosk).json()["status"] == "in_kitchen"
        print("3. bank confirmation at the cloud applied by the hub; order went to the kitchen")

        # 4. Internet down: the cloud is unreachable. The restaurant keeps working.
        stop(cloud)
        staff = h.get("/v1/staff", headers=till).json()
        nimal = next(s for s in staff if s["name"] == "Nimal")
        pin = h.post(
            "/v1/staff/pin-login", headers=till, json={"staff_id": nimal["id"], "pin": "1111"}
        ).json()
        cashier = {**till, "Authorization": f"Bearer {pin['staff_token']}"}
        h.post("/v1/shifts/open", headers=cashier, json={"opening_float": 0})
        offline_tokens = []
        for _ in range(3):
            o2 = h.post("/v1/orders", headers=cashier, json={"items": [line]}).json()
            paid = h.post(
                f"/v1/orders/{o2['id']}/payments/cash", headers=cashier, json={"tendered": o2["total"]}
            )
            assert paid.status_code == 201, paid.text
            h.post(f"/v1/kds/orders/{o2['id']}/bump", headers=kds)
            offline_tokens.append(o2["token"])
        until("hub notices", lambda: not h.get("/v1/sync/status").json()["cloud_online"], 15)
        r = h.post("/v1/orders", headers=kiosk, json={"items": [line]}).json()
        qr_off = h.post(f"/v1/orders/{r['id']}/payments/lankaqr", headers=kiosk)
        assert qr_off.json()["error"]["code"] == "lankaqr_unavailable", "no bank without internet"
        print(f"4. internet down: {len(offline_tokens)} cash orders taken, cooked and bumped; LankaQR off")

        # 5. Internet back: everything arrives at the cloud, once.
        cloud = serve(CLOUD, CLOUD_ENV)
        until(
            "hub sent everything",
            lambda: (
                h.get("/v1/sync/status").json()["pending"] == 0
                and h.get("/v1/sync/status").json()["cloud_online"]
            ),
            30,
        )
        sales = c.get(f"{base}/reports/sales", headers=inst).json()
        assert sales["orders"] == 4, sales  # the QR order + 3 cash orders
        csv = c.get(f"{base}/reports/orders.csv", headers=inst).text
        for t in offline_tokens:
            assert csv.count(f",{t},") == 1, f"{t} exactly once"
        print("5. internet back: all orders reached the cloud exactly once")

        # 6. Hub down: screens use the cloud directly (backup numbers from 500).
        stop(hub)
        hub = None
        backup = until(
            "cloud takes over",
            lambda: (
                (r := c.post("/v1/orders", headers=cashier, json={"items": [line]})).status_code == 201
                and r.json()
            ),
            20,
        )
        assert int(backup["token"][1:]) >= 500, backup["token"]
        cash = c.post(
            f"/v1/orders/{backup['id']}/payments/cash", headers=cashier, json={"tendered": backup["total"]}
        )
        assert cash.status_code == 201, cash.text
        hub = serve(HUB, HUB_ENV)
        until(
            "hub caught up",
            lambda: h.get(f"/v1/orders/{backup['id']}", headers=cashier).status_code == 200,
            30,
        )
        until("hub in charge again", lambda: c.get("/v1/menu", headers=kiosk).status_code == 409, 30)
        print(f"6. hub down: cloud took order {backup['token']}; hub back, caught up, in charge again")

        # 7. A kiosk page served by the hub: Local, then Cloud when the hub dies, then Local again.
        browser = Browser(WORK / "chrome", 9340)
        k = screen("kiosk", "Kiosk Browser")
        tab = browser.tab(f"{HUB_URL}/kiosk?slot=hyb", "kioskH", 1080, 1500)
        saved = f"JSON.stringify({{token: {k['X-Device-Token']!r}, device: {{type: 'kiosk'}}}})"
        tab.js(f"localStorage.setItem('kiosk:dev:kiosk:hyb', {saved})")
        tab.send("Page.reload")
        tab.wait_text("Tap to order", 20)
        tab.click("English", "span[role=button]")  # the status pill is on the menu screens
        tab.wait("document.querySelector('[data-via]')?.dataset.via === 'hub'", 15)
        tab.wait_text("Live · Local", 15)
        tab.shot(OUT, "h1-kiosk-local")
        stop(hub)
        hub = None
        tab.wait("document.querySelector('[data-via]')?.dataset.via === 'cloud'", 40)
        tab.wait_text("Cloud (hub down)", 30)
        tab.click("Drinks", "nav button")
        tab.click("Lime Juice", "button[data-item]")
        tab.click("Review order")
        tab.click("Confirm order")
        tab.wait_text("Pay here by QR", 15)
        tab.shot(OUT, "h2-kiosk-cloud-backup")
        hub = serve(HUB, HUB_ENV)
        tab.wait("document.querySelector('[data-via]')?.dataset.via === 'hub'", 60)
        tab.shot(OUT, "h3-kiosk-back-local")
        print("7. browser kiosk: Local -> Cloud (hub down, still ordering) -> Local by itself")
        print("OK: hybrid hub + cloud passed")
    finally:
        if browser:
            browser.close()
        for p in (hub, cloud):
            if p and p.poll() is None:
                stop(p)
        shutil.rmtree(WORK, ignore_errors=True)  # Chrome profiles are big


if __name__ == "__main__":
    main()
