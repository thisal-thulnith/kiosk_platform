"""Each restaurant has its own look: main colour, logo and light / dark screens."""

from tests.conftest import Api


async def test_brand_reaches_every_screen(api: Api) -> None:
    c = api.client
    kiosk = await api.device("Kiosk 1", "kiosk")
    me = (await c.get("/v1/devices/me", headers=kiosk)).json()
    assert me["venue"]["brand"] == {"color": "#f5a524", "logo_url": None, "theme": "light"}
    for bad in ({"brand_color": "red"}, {"logo_url": "javascript:alert(1)"}, {"theme": "neon"}):
        r = await c.patch(api.av(""), headers=api.admin, json={"settings": bad})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_setting", bad
    look = {"brand_color": "#0f766e", "logo_url": "/media/x/logo.png", "theme": "dark"}
    assert (await c.patch(api.av(""), headers=api.admin, json={"settings": look})).status_code == 200
    me = (await c.get("/v1/devices/me", headers=kiosk)).json()
    assert me["venue"]["brand"] == {"color": "#0f766e", "logo_url": "/media/x/logo.png", "theme": "dark"}
