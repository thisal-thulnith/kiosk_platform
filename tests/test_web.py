"""Clean addresses: each restaurant has its own path (/demo/pos, /demo/owner…), our console is
/platform, a tablet starts at /. Old addresses (installed apps, QR codes, bookmarks) redirect."""

import pytest

from tests.conftest import Api


async def test_clean_addresses_and_old_ones(api: Api) -> None:
    c = api.client
    for url in (
        "/",
        "/platform",
        "/demo/pos",
        "/demo/kitchen",
        "/demo/board",
        "/demo/owner",
        "/demo/setup",
        "/pos",
    ):
        r = await c.get(url)
        assert r.status_code == 200 and "<!doctype html>" in r.text.lower(), url
    assert "<!doctype html>" in (await c.get("/demo")).text.lower(), "a restaurant's sign-in page"
    for url in ("/demo/nope", "/de mo/pos", "/a.b"):
        assert (await c.get(url)).status_code == 404, url
    assert (await c.get("/sw.js")).status_code == 200
    assert (await c.get("/manifest.webmanifest")).status_code == 200
    cases = {
        "/screens/": "/",
        "/screens/app.html?pair=123456": "/?pair=123456",
        "/screens/cashier.html?slot=2": "/pos?slot=2",
        "/screens/index.html?venue=v1": "/setup?venue=v1",
        "/screens/owner.html": "/owner",
        "/screens/kds.html": "/kitchen",
        "/screens/ui/status/": "/board",
        "/screens/table.html": "/table",
    }
    for old, new in cases.items():
        r = await c.get(old, follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == new, (old, r.headers.get("location"))
    assert (await c.get("/screens/nope.html", follow_redirects=False)).status_code == 404


async def test_admin_address(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """With ADMIN_HOST set, our team's consoles and login live only on admin.<domain>."""
    from kiosk.config import settings

    c = api.client
    monkeypatch.setattr(settings, "admin_host", "admin.example.com")
    monkeypatch.setattr(settings, "public_url", "https://app.example.com")
    app = {"host": "app.example.com"}
    admin = {"host": "admin.example.com"}
    for path in ("/platform", "/demo/setup", "/demo/owner", "/owner"):
        r = await c.get(path, headers=app, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == f"https://admin.example.com{path}", path
    r = await c.post("/v1/platform/auth/login", headers=app, json={"email": "x@y.z", "password": "x"})
    assert r.status_code == 404, "the team login isn't on the restaurants' address"
    assert (
        await c.post("/v1/platform/auth/login", headers=admin, json={"email": "x@y.z", "password": "x"})
    ).status_code == 401
    assert "<!doctype html>" in (await c.get("/", headers=admin)).text.lower()  # the Platform console
    assert (await c.get("/demo/setup", headers=admin)).status_code == 200
    r = await c.get("/demo/pos?slot=2", headers=admin, follow_redirects=False)
    assert r.headers["location"] == "https://app.example.com/demo/pos?slot=2"
    assert (await c.get("/demo/pos", headers=app)).status_code == 200
    assert (await c.get("/demo/owner", headers=admin)).status_code == 200  # owners log in here too
    # One login: on the restaurants' address a team account isn't found (owners' accounts are).
    team = {"email": "platform@kiosk.lk", "password": "platform12345"}
    assert (await c.post("/v1/auth/login", headers=app, json=team)).status_code == 401
    assert (await c.post("/v1/auth/login", headers=admin, json=team)).json()["kind"] == "installer"
    f = (await c.get("/v1/features", headers=app)).json()
    assert f["app_url"] == "https://app.example.com" and f["admin_url"] == "https://admin.example.com"
