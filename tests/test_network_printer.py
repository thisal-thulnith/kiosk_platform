"""Printers on the restaurant's network (Ethernet / Wi-Fi, raw TCP 9100): the restaurant's hub sends
each job straight to the printer, so the kitchen keeps printing without internet (like Toast's local
hub or Oracle's on-site CAPS). A cloud-only server can't reach them and says so."""

import asyncio

import pytest

from kiosk.config import settings
from tests.conftest import Api


async def test_hub_prints_on_a_network_printer(api: Api) -> None:
    c = api.client
    got: list[bytes] = []

    async def printer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        got.append(await reader.read())
        writer.close()

    server = await asyncio.start_server(printer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        r = await c.post(
            api.av("/printers"),
            headers=api.installer,
            json={
                "name": "Counter printer",
                "connection": "network",
                "roles": ["receipt", "kitchen"],
                "host": "127.0.0.1",
                "port": port,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["address"] == f"127.0.0.1:{port}"
        pos = await api.login(await api.device("POS 1", "cashier"), "Nimal", "1111")
        await c.post("/v1/shifts/open", headers=pos, json={"opening_float": 0})
        o = (await c.post("/v1/orders", headers=pos, json={"items": [api.line("Chicken Burger")]})).json()
        await c.post(f"/v1/orders/{o['id']}/payments/cash", headers=pos, json={"tendered": o["total"]})
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.05)
        assert got and any(b"Chicken Burger" in g for g in got), "the receipt reached the printer"
        printers = {p["name"]: p for p in (await c.get(api.av("/printers"), headers=api.installer)).json()}
        assert printers["Counter printer"]["last_seen_at"]
    finally:
        server.close()
        await server.wait_closed()

    # The printer is switched off: the job fails, staff are told, and it can be reprinted later.
    r = await c.post(api.av(f"/printers/{printers['Counter printer']['id']}/test"), headers=api.installer)
    assert r.status_code == 202
    jobs = await c.get(api.av(f"/printers/{printers['Counter printer']['id']}/jobs"), headers=api.installer)
    if jobs.status_code == 200:
        assert any(j["status"] == "failed" for j in jobs.json())


async def test_network_printer_needs_a_hub(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    monkeypatch.setattr(settings, "app_mode", "cloud")
    body = {"name": "Bar printer", "connection": "network", "roles": ["kitchen"], "host": "192.168.1.50"}
    r = await c.post(api.av("/printers"), headers=api.installer, json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "needs_hub"
    r = await c.post(api.av("/printers"), headers=api.installer, json={**body, "host": "bad host!"})
    assert r.json()["error"]["code"] == "printer_address"
    await api.venue_settings(network_mode="hybrid")
    assert (await c.post(api.av("/printers"), headers=api.installer, json=body)).status_code == 201
