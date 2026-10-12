"""Tiny Chrome DevTools helper for the screen tests: a headless Chrome, tabs, clicks, screenshots."""

import base64
import contextlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import httpx
from websockets.sync.client import connect

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-X110) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


# Menus change by time of day (e.g. a Breakfast category in the morning), so a dish may be on another
# category page: for ".tile" clicks, page through the category chips until the dish is shown.
SHOW_TILE = (
    "(() => {{ const has = () => [...document.querySelectorAll('.tile')]"
    ".some(t => t.textContent.includes({t}));"
    " if (has()) return true; for (const c of document.querySelectorAll('.chips .chip')) {{ c.click();"
    " if (has()) return true; }} return false; }})()"
)


class Tab:
    def __init__(self, ws_url: str, name: str) -> None:
        self.ws = connect(ws_url, max_size=50_000_000).__enter__()
        self.name, self.n = name, 0
        self.errors: list[str] = []
        self.send("Runtime.enable")
        self.send("Page.enable")

    def send(self, method: str, **params: Any) -> Any:
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(json.dumps(msg["params"]["exceptionDetails"])[:300])
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")

    def js(self, expr: str) -> Any:
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"{self.name}: {r['exceptionDetails']}")
        return r["result"].get("value")

    def text(self) -> str:
        try:
            return self.js("document.body ? document.body.innerText : ''") or ""
        except RuntimeError:
            return ""

    def url(self) -> str:
        return str(self.js("location.pathname + location.search"))

    def wait(self, check: str, timeout: float = 10) -> None:
        """Wait until a JS expression is truthy (wrap DOM lookups in !! so they return a boolean)."""
        self.to_front()
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.js(check):
                    return
            except RuntimeError:
                pass
            time.sleep(0.25)
        raise RuntimeError(f"{self.name}: {check!r} never became true. Body: {self.text()[:600]}")

    def wait_text(self, text: str, timeout: float = 10) -> None:
        self.to_front()
        end = time.time() + timeout
        while time.time() < end:
            if text.lower() in self.text().lower():
                return
            time.sleep(0.25)
        with contextlib.suppress(Exception):
            self.shot(Path(tempfile.gettempdir()), f"fail-{self.name}")
        raise RuntimeError(f"{self.name}: {text!r} never appeared. Body: {self.text()[:600]}")

    front: "Tab | None" = None

    def to_front(self) -> None:
        """Like a person looking at this screen: the browser only animates the tab in front."""
        if Tab.front is not self:
            self.send("Page.bringToFront")
            Tab.front = self
            time.sleep(0.15)

    def click(self, text: str, sel: str = "button", timeout: float = 8) -> None:
        self.to_front()
        expr = (
            f"(() => {{ const b = [...document.querySelectorAll({json.dumps(sel)})]"
            f".find(b => b.textContent.includes({json.dumps(text)})"
            " && !b.disabled && b.getClientRects().length > 0);"
            " if (!b) return false; b.click(); return true; })()"
        )
        end = time.time() + timeout
        while time.time() < end:
            if sel == ".tile":
                self.js(SHOW_TILE.format(t=json.dumps(text)))
            if self.js(expr):
                return
            time.sleep(0.2)
        with contextlib.suppress(Exception):  # a picture of what was on screen, for the failure
            self.shot(Path(tempfile.gettempdir()), f"fail-{self.name}")
        raise RuntimeError(f"{self.name}: no visible {sel} {text!r}. Body: {self.text()[:600]}")

    def shot(self, out: Path, label: str) -> None:
        self.to_front()  # background tabs don't run animations (windows look faded)
        time.sleep(0.35)
        data = self.send("Page.captureScreenshot", format="png")["data"]
        (out / f"{label}.png").write_bytes(base64.b64decode(data))


class Browser:
    def __init__(self, profile: Path, port: int) -> None:
        self.port = port
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}"]
            + ["--no-first-run", "--disable-gpu"]
            # Many screens are open as tabs at once: keep background tabs animating like real screens.
            + ["--disable-background-timer-throttling", "--disable-renderer-backgrounding"]
            + ["--disable-backgrounding-occluded-windows", "about:blank"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version")
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("Chrome did not start")

    def tab(self, url: str, name: str, w: int, hgt: int, android: bool = False) -> Tab:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        t = Tab(json.loads(urllib.request.urlopen(req).read())["webSocketDebuggerUrl"], name)
        t.send("Emulation.setDeviceMetricsOverride", width=w, height=hgt, deviceScaleFactor=1, mobile=android)
        if android:
            t.send("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
            t.send("Emulation.setUserAgentOverride", userAgent=ANDROID_UA, platform="Android")
        t.send("Page.navigate", url=url)
        time.sleep(1.2)
        return t

    def close(self) -> None:
        try:
            info = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version").read())
            with connect(info["webSocketDebuggerUrl"]) as ws:
                ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            self.proc.wait(10)
        except Exception:  # noqa: BLE001
            self.proc.terminate()
            self.proc.wait(10)


def start_server(port: int, env: dict[str, str]) -> subprocess.Popen[bytes]:
    """initdb + seed + serve on a fresh database described by env."""
    full = {**os.environ, **env}
    subprocess.run(["uv", "run", "kiosk", "initdb"], env=full, check=True, capture_output=True)
    subprocess.run(["uv", "run", "kiosk", "seed"], env=full, check=True, capture_output=True)
    proc = subprocess.Popen(
        ["uv", "run", "kiosk", "serve", "--host", "127.0.0.1", "--port", str(port)],
        env=full,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        try:
            httpx.get(f"http://127.0.0.1:{port}/v1/health", timeout=1)
            return proc
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError("server did not start")
