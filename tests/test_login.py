"""One login screen for our team and restaurant owners: the account decides which console opens.
Our team's accounts need a phone code (2-step, like Google Authenticator) in prod."""

import time

import pytest

from kiosk.auth import totp
from kiosk.config import settings
from tests.conftest import Api

TEAM = {"email": "platform@kiosk.lk", "password": "platform12345"}


async def test_one_login_for_team_and_owners(api: Api) -> None:
    c = api.client
    team = (await c.post("/v1/auth/login", json=TEAM)).json()
    assert team["kind"] == "installer"
    assert (
        await c.get("/v1/platform/tenants", headers={"Authorization": f"Bearer {team['access_token']}"})
    ).status_code == 200
    owner = (await c.post("/v1/auth/login", json={"email": "ADMIN@demo.lk", "password": "admin12345"})).json()
    assert owner["kind"] == "admin" and owner["role"] == "owner"
    venues = await c.get("/v1/admin/venues", headers={"Authorization": f"Bearer {owner['access_token']}"})
    assert venues.status_code == 200 and venues.json()
    r = await c.post("/v1/auth/login", json={**TEAM, "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["message"] == "Wrong email or password"


async def test_team_two_step(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    c = api.client
    monkeypatch.setattr(settings, "team_2fa", True)
    # First login: no token yet, set up the authenticator app from the QR code.
    first = (await c.post("/v1/auth/login", json=TEAM)).json()
    assert first["need"] == "setup" and "access_token" not in first
    assert first["uri"].startswith("otpauth://totp/") and first["secret"] in first["uri"]
    bad = await c.post("/v1/auth/two-step", json={"setup_token": first["setup_token"], "otp": "000000"})
    assert bad.status_code == 401
    now = totp.code_now(first["secret"])
    done = (await c.post("/v1/auth/two-step", json={"setup_token": first["setup_token"], "otp": now})).json()
    assert done["kind"] == "installer" and done["two_step"]

    # Every login after: password, then the phone code. A used code can't be used again.
    assert (await c.post("/v1/auth/login", json=TEAM)).json() == {"need": "otp"}
    assert (await c.post("/v1/auth/login", json={**TEAM, "otp": now})).status_code == 401
    later = totp.code_now(first["secret"], time.time() + 30)
    r = await c.post("/v1/auth/login", json={**TEAM, "otp": later})
    assert r.status_code == 200 and r.json()["access_token"]
    # The older team login asks for the code too.
    assert (await c.post("/v1/platform/auth/login", json=TEAM)).json() == {"need": "otp"}
    # Owners don't need it.
    owner = await c.post("/v1/auth/login", json={"email": "admin@demo.lk", "password": "admin12345"})
    assert owner.json()["kind"] == "admin"


def test_totp_matches_rfc_6238() -> None:
    # RFC 6238 test secret "12345678901234567890" (SHA-1), T = 59 s -> 94287082 (8 digits; 6 = 287082).
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_now(secret, 59) == "287082"
    assert totp.code_now(secret, 1111111109) == "081804"
