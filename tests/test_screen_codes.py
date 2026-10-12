"""Screen sign-in, like Square device codes: the restaurant's address + the screen's own code. It
works for good, only at its own restaurant, signs the previous tablet out, and can be reset."""

from tests.conftest import Api


async def test_screen_code_sign_in(api: Api) -> None:
    c = api.client
    r = await c.post(
        api.av("/devices"), headers=api.installer, json={"type": "table", "name": "T9", "table_ref": "T9"}
    )
    code = r.json()["screen_code"]
    assert len(code) == 12 and code[4] == "-" and not set(code) & set("01ILO"), code
    devices = {d["name"]: d for d in (await c.get(api.av("/devices"), headers=api.installer)).json()}
    assert devices["T9"]["screen_code"] == code, "the Setup console shows it again"
    venue_code = (await c.get(api.av(""), headers=api.admin)).json()["code"]

    async def sign_in(venue: str, typed: str) -> tuple[int, dict]:
        r = await c.post(
            "/v1/devices/sign-in", json={"venue": venue, "code": typed, "client": {"install_id": "a"}}
        )
        return r.status_code, r.json()

    # Typed loosely (lower case, no dashes) is fine; the wrong restaurant or code is not.
    st, first = await sign_in(venue_code.lower(), code.replace("-", "").lower())
    assert st == 200 and first["device"]["table_ref"] == "T9" and not first["replaced_another_device"], first
    assert (await sign_in("other", code))[0] == 400
    assert (await sign_in(venue_code, "AAAA-BBBB-CC"))[0] == 400
    tablet1 = {"X-Device-Token": first["device_token"]}
    assert (await c.get("/v1/devices/me", headers=tablet1)).status_code == 200

    # The same code on another tablet: that one is in, the first one is out.
    st, second = await sign_in(venue_code, code)
    assert st == 200 and second["replaced_another_device"]
    r = await c.get("/v1/devices/me", headers=tablet1)
    assert r.status_code == 401 and r.json()["error"]["code"] == "device_not_set_up"
    tablet2 = {"X-Device-Token": second["device_token"]}
    assert (await c.get("/v1/devices/me", headers=tablet2)).status_code == 200

    # Reset in the Setup console: the old code stops working and the tablet is signed out.
    device_id = devices["T9"]["id"]
    new = (await c.post(api.av(f"/devices/{device_id}/screen-code"), headers=api.installer)).json()[
        "screen_code"
    ]
    assert new != code
    assert (await c.get("/v1/devices/me", headers=tablet2)).status_code == 401
    assert (await sign_in(venue_code, code))[0] == 400
    assert (await sign_in(venue_code, new))[0] == 200
    # Only our installers reset codes.
    r = await c.post(api.av(f"/devices/{device_id}/screen-code"), headers=api.admin)
    assert r.status_code == 403
