from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api import limits
from kiosk.api.deps import Ctx, Uow
from kiosk.auth.security import (
    issue_jwt,
    new_token,
    token_digest,
    verify_secret,
)
from kiosk.config import settings
from kiosk.errors import AppError, Unauthorized
from kiosk.infra.lan import lan_url
from kiosk.infra.models import AdminUser, Device, Staff, Venue, utcnow
from kiosk.services import hybrid, logins, screen_codes, tables
from kiosk.services.payments import card_setup, method_on
from kiosk.services.serializers import staff_dict
from kiosk.services.uow import Actor

router = APIRouter(prefix="/v1", tags=["auth"])

MAX_PIN_ATTEMPTS = 5
PIN_LOCK_MINUTES = 5


class AdminLogin(BaseModel):
    email: str
    password: str


class Login(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)
    otp: str | None = Field(default=None, max_length=12, description="The phone code, when asked for")


class TwoStepSetup(BaseModel):
    setup_token: str = Field(max_length=2000)
    otp: str = Field(max_length=12)


@router.post("/auth/login")
async def login(body: Login, request: Request, uow: Uow) -> dict[str, Any]:
    """One login for our team and restaurant owners / managers. `kind` says which console opens:
    "installer" (Platform) or "admin" (Owner app). Team accounts may answer `{"need": "otp"}`
    (send again with the phone code) or `{"need": "setup", ...}` (turn on 2-step first)."""
    return await logins.login(uow, request, body.email, body.password, body.otp)


@router.post("/auth/two-step")
async def two_step_setup(body: TwoStepSetup, request: Request, uow: Uow) -> dict[str, Any]:
    """Finish turning on 2-step: the first code from the authenticator app."""
    return await logins.finish_setup(uow, request, body.setup_token, body.otp)


@router.post("/admin/auth/login")
async def admin_login(body: AdminLogin, request: Request, uow: Uow) -> dict[str, Any]:
    """A restaurant owner or manager only (older apps). New logins use /v1/auth/login."""
    limits.check(request, "login")
    admin = await uow.session.scalar(select(AdminUser).where(AdminUser.email == body.email.lower()))
    if admin is None or not admin.is_active or not verify_secret(body.password, admin.password_hash):
        limits.failed(request, "login")
        raise Unauthorized("Wrong email or password")
    token = issue_jwt(
        {"sub": admin.id, "typ": "admin", "tenant_id": admin.tenant_id, "role": admin.role},
        settings.admin_session_hours,
    )
    return {"access_token": token, "token_type": "bearer", "tenant_id": admin.tenant_id}


async def _through_cloud(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """On the restaurant's hub: codes live in the cloud. Ask the cloud, then pull the config at once
    so this hub knows the new screen's key hash before the screen's first request."""
    import httpx

    from kiosk.sync import edge

    async with httpx.AsyncClient(base_url=settings.cloud_url or "", timeout=10) as client:
        try:
            r = await client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise AppError("cloud_unreachable", "Signing in a screen needs the internet once", 503) from exc
        if r.status_code != 200:
            err = r.json().get("error", {}) if "json" in r.headers.get("content-type", "") else {}
            raise AppError(
                err.get("code", "bad_screen_code"), err.get("message", "Sign-in failed"), r.status_code
            )
        await edge.pull_once(client)
    result: dict[str, Any] = r.json()
    return result


async def _pair_through_cloud(code: str, client_info: "ClientInfo | None" = None) -> dict[str, Any]:
    """On the restaurant's hub: setup codes live in the cloud. Ask the cloud, then pull the config at
    once so this hub knows the new screen's key hash before the screen's first request."""
    import httpx

    from kiosk.sync import edge

    async with httpx.AsyncClient(base_url=settings.cloud_url or "", timeout=10) as client:
        try:
            body = {"code": code, "client": client_info.model_dump() if client_info else None}
            r = await client.post("/v1/devices/pair", json=body)
        except httpx.HTTPError as exc:
            raise AppError("cloud_unreachable", "Setting up a screen needs the internet once", 503) from exc
        if r.status_code != 200:
            err = r.json().get("error", {}) if "json" in r.headers.get("content-type", "") else {}
            raise AppError(
                err.get("code", "bad_pairing_code"), err.get("message", "Pairing failed"), r.status_code
            )
        await edge.pull_once(client)
    result: dict[str, Any] = r.json()
    return result


async def network_for_screens(uow: Uow, venue: Venue) -> dict[str, Any]:
    """Addresses a screen may use. A hybrid venue's screens use the hub first, then the cloud."""
    mode = venue.setting("network_mode")
    if settings.app_mode == "cloud":
        row = await hybrid.status_row(uow, venue.id)
        hub_url = row.lan_url if row and mode == "hybrid" else None
        cloud_url = settings.public_url
    else:
        hub_url, cloud_url = lan_url(), settings.cloud_url
    return {
        "mode": mode,
        "hub_url": hub_url,
        "cloud_url": cloud_url,
        "served_by": "cloud" if settings.app_mode == "cloud" else "hub",
    }


class ClientInfo(BaseModel):
    """What the physical tablet is, so the installer can tell screens apart in the Setup console."""

    install_id: str | None = Field(default=None, max_length=64, description="Made once per app install")
    app: str | None = Field(default=None, max_length=40, description="web | android")
    app_version: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=80)
    os: str | None = Field(default=None, max_length=80)
    browser: str | None = Field(default=None, max_length=80)
    screen: str | None = Field(default=None, max_length=20, description="e.g. 1920x1200")
    page: str | None = Field(default=None, max_length=200, description="Address the screen runs at")


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    client: ClientInfo | None = None


def remember_client(device: Device, info: ClientInfo | None, request: Request, paired: bool = False) -> None:
    old = (device.settings or {}).get("client") or {}
    new = {**old, **(info.model_dump(exclude_none=True) if info else {})}
    new["ip"] = request.client.host if request.client else None
    if paired:
        new["paired_at"] = utcnow().isoformat()
    if new != old:
        device.settings = {**(device.settings or {}), "client": new}  # new dict: JSON change is saved


@router.post("/devices/pair", tags=["devices"])
async def pair_device(body: PairRequest, request: Request, uow: Uow) -> dict[str, Any]:
    """Exchange a 6-digit pairing code (shown in the admin portal) for a device token.

    The token is returned once. Only its hash is stored. Wrong codes are limited per address.
    """
    limits.check(request, "pair")
    device = await uow.session.scalar(select(Device).where(Device.pairing_code == body.code))
    if device is None and settings.is_edge and settings.cloud_url and settings.cloud_sync_key:
        return await _pair_through_cloud(body.code)
    if device is None or device.pairing_expires_at is None or device.pairing_expires_at < utcnow():
        limits.failed(request, "pair")
        raise AppError("bad_pairing_code", "Pairing code is wrong or expired", 400)
    token = new_token()
    device.token_hash = token_digest(token)
    device.pairing_code = None
    device.pairing_expires_at = None
    device.last_seen_at = utcnow()
    remember_client(device, body.client, request, paired=True)
    uow.audit(Actor(venue_id=device.venue_id, device_id=device.id), "device.paired", device.id)
    venue = await uow.session.get(Venue, device.venue_id)
    if venue is not None:
        venue.config_version += 1  # the restaurant's hub learns the new screen's key hash
    await uow.commit()
    return {
        "device_token": token,
        "device": {
            "id": device.id,
            "type": device.type,
            "name": device.name,
            "venue_id": device.venue_id,
            "venue_code": venue.code if venue is not None else None,  # for the screen's address
            "station": device.station,
            "table_ref": device.table_ref,
        },
    }


class HeartbeatIn(BaseModel):
    client: ClientInfo | None = None


class SignInRequest(BaseModel):
    venue: str = Field(
        min_length=2, max_length=20, description="The restaurant's code, from its address (/demo)"
    )
    code: str = Field(min_length=10, max_length=20, description="The screen code, e.g. K7MQ-4XPA-2R")
    client: ClientInfo | None = None


@router.post("/devices/sign-in", tags=["devices"])
async def sign_in_device(body: SignInRequest, request: Request, uow: Uow) -> dict[str, Any]:
    """Sign a device in with its restaurant's address + its screen code (like Square device codes).

    The device gets its own key and stays signed in. A code only works at its own restaurant, for
    its own screen. Signing in on another device signs the previous one out. Wrong codes are
    rate-limited per network address.
    """
    limits.check(request, "pair")
    device = await screen_codes.find(uow, body.code)
    venue = await uow.session.get(Venue, device.venue_id) if device else None
    if device is None and settings.is_edge and settings.cloud_url and settings.cloud_sync_key:
        return await _through_cloud("/v1/devices/sign-in", body.model_dump())
    if device is None or venue is None or venue.code.lower() != body.venue.strip().lower():
        limits.failed(request, "pair")
        raise AppError("bad_screen_code", "That screen code is not right for this restaurant", 400)
    if not device.is_active:
        raise AppError("screen_turned_off", "This screen is turned off in the Setup console", 403)
    token = new_token()
    replaced = device.token_hash is not None
    device.token_hash = token_digest(token)  # the previous device's key stops working now
    device.pairing_code = device.pairing_expires_at = None
    device.last_seen_at = utcnow()
    remember_client(device, body.client, request, paired=True)
    uow.audit(Actor(venue_id=venue.id, device_id=device.id), "device.signed_in", device.id, replaced=replaced)
    venue.config_version += 1  # the restaurant's hub learns the new key hash
    await uow.commit()
    return {
        "device_token": token,
        "device": {
            "id": device.id,
            "type": device.type,
            "name": device.name,
            "venue_id": device.venue_id,
            "venue_code": venue.code,
            "station": device.station,
            "table_ref": device.table_ref,
        },
        "replaced_another_device": replaced,
    }


@router.post("/devices/heartbeat", tags=["devices"])
async def heartbeat(ctx: Ctx, uow: Uow, request: Request, body: HeartbeatIn | None = None) -> dict[str, Any]:
    ctx.device.last_seen_at = utcnow()
    remember_client(ctx.device, body.client if body else None, request)
    await uow.commit()
    return {"ok": True, "server_time": utcnow().isoformat()}


@router.get("/devices/me", tags=["devices"])
async def me(ctx: Ctx, uow: Uow) -> dict[str, Any]:
    d = ctx.device
    return {
        # Where to talk to: the restaurant's hub (local network) first when it has one, else the cloud.
        "network": await network_for_screens(uow, ctx.venue),
        # Table screens: is this table open for ordering (staff open tables, or always open)?
        "table": {
            "ref": d.table_ref,
            "access": ctx.venue.setting("table_access"),
            "open": await tables.is_open(uow, ctx.venue, d.table_ref),
        }
        if d.type == "table" and d.table_ref
        else None,
        "device": {
            "id": d.id,
            "type": d.type,
            "name": d.name,
            "station": d.station,
            "table_ref": d.table_ref,
        },
        "venue": {
            "id": ctx.venue.id,
            "name": ctx.venue.name,
            "code": ctx.venue.code,
            "timezone": ctx.venue.timezone,
            "languages": ctx.venue.setting("languages"),
            "release_rule": ctx.venue.setting("release_rule"),
            "dine_in_mode": ctx.venue.setting("dine_in_mode"),
            "serve_mode": ctx.venue.setting("serve_mode"),
            "attract_images": ctx.venue.setting("attract_images"),
            "brand": {
                "color": ctx.venue.setting("brand_color"),
                "logo_url": ctx.venue.setting("logo_url") or None,
                "theme": ctx.venue.setting("theme"),
            },
            "board_page_seconds": ctx.venue.setting("board_page_seconds"),
        },
        # Modules in the venue's package (None = unrestricted demo venue); screens hide what isn't sold.
        "modules": (ctx.venue.plan or {}).get("modules"),
        # What this screen can offer at checkout.
        "payments": {
            "cash": method_on(ctx.venue, "cash"),
            "lankaqr": method_on(ctx.venue, "lankaqr"),
            "card": (card_setup(d) or {}).get("mode") if method_on(ctx.venue, "card") else None,
        },
        "staff": staff_dict(ctx.staff) if ctx.staff else None,
    }


@router.get("/staff", tags=["staff"])
async def list_staff(ctx: Ctx, uow: Uow) -> list[dict[str, Any]]:
    """Names for the PIN login screen."""
    rows = (
        await uow.session.scalars(
            select(Staff).where(Staff.venue_id == ctx.venue.id, Staff.is_active).order_by(Staff.name)
        )
    ).all()
    return [staff_dict(s) for s in rows]


class PinLogin(BaseModel):
    staff_id: str
    pin: str = Field(min_length=4, max_length=8)


@router.post("/staff/pin-login", tags=["staff"])
async def pin_login(body: PinLogin, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    staff = await uow.session.get(Staff, body.staff_id)
    if staff is None or staff.venue_id != ctx.venue.id or not staff.is_active:
        raise Unauthorized("Wrong staff or PIN")
    now = utcnow()
    if staff.locked_until and staff.locked_until > now:
        raise AppError("pin_locked", "Too many wrong PINs. Try again in a few minutes", 423)
    if not verify_secret(body.pin, staff.pin_hash):
        staff.failed_pin_attempts += 1
        if staff.failed_pin_attempts >= MAX_PIN_ATTEMPTS:
            staff.locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
            staff.failed_pin_attempts = 0
            uow.audit(ctx.actor, "staff.pin_locked", staff.id)
        await uow.commit()
        raise Unauthorized("Wrong staff or PIN")
    staff.failed_pin_attempts = 0
    staff.locked_until = None
    uow.audit(ctx.actor, "staff.login", staff.id)
    await uow.commit()
    token = issue_jwt(
        {"sub": staff.id, "typ": "staff", "device_id": ctx.device.id, "role": staff.role},
        settings.staff_session_hours,
    )
    return {"staff_token": token, "token_type": "bearer", "staff": staff_dict(staff)}
