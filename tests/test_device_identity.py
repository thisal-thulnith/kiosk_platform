"""Each screen knows which physical tablet it is on (model, system, app, screen, address), and the
Setup console warns when one tablet is set up as two screens."""

from tests.conftest import Api

TAB = {"install_id": "inst-1", "app": "web", "model": "SM-X205", "os": "Android 14", "screen": "1920x1200"}


async def test_pairing_records_the_tablet(api: Api) -> None:
    c = api.client

    async def setup(name: str, type_: str, client: dict[str, str], **extra: str) -> dict[str, str]:
        r = await c.post(
            api.av("/devices"), headers=api.installer, json={"type": type_, "name": name, **extra}
        )
        p = await c.post("/v1/devices/pair", json={"code": r.json()["pairing_code"], "client": client})
        assert p.status_code == 200, p.text
        return {"X-Device-Token": p.json()["device_token"]}

    t1 = await setup("Table T1", "table", TAB, table_ref="T1")
    r = await c.post("/v1/devices/heartbeat", headers=t1, json={"client": {**TAB, "app_version": "1.2.0"}})
    assert r.status_code == 200
    assert (await c.post("/v1/devices/heartbeat", headers=t1)).status_code == 200, "body is optional"
    await setup("Kiosk 1", "kiosk", {"install_id": "inst-2"})
    devices = {d["name"]: d for d in (await c.get(api.av("/devices"), headers=api.installer)).json()}
    info = devices["Table T1"]["client"]
    assert info["model"] == "SM-X205" and info["app_version"] == "1.2.0" and info["ip"] and info["paired_at"]
    assert devices["Table T1"]["same_tablet_as"] == []

    await setup("Table T2", "table", TAB, table_ref="T2")  # the same tablet, set up again as T2
    devices = {d["name"]: d for d in (await c.get(api.av("/devices"), headers=api.installer)).json()}
    assert devices["Table T2"]["same_tablet_as"] == ["Table T1"]
    assert devices["Kiosk 1"]["same_tablet_as"] == []
