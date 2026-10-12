from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.auth.security import read_jwt, token_digest
from kiosk.config import settings
from kiosk.errors import AppError, Forbidden, NotFound, Unauthorized
from kiosk.infra.db import get_session
from kiosk.infra.models import AdminUser, Device, PlatformUser, Staff, Venue
from kiosk.services import hybrid
from kiosk.services.uow import Actor, UnitOfWork


async def get_uow(session: Annotated[AsyncSession, Depends(get_session)]) -> AsyncIterator[UnitOfWork]:
    yield UnitOfWork(session)


Uow = Annotated[UnitOfWork, Depends(get_uow)]


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


# ------------------------------------------------------------------ devices + staff


@dataclass
class DeviceCtx:
    device: Device
    venue: Venue
    staff: Staff | None = None

    @property
    def actor(self) -> Actor:
        return Actor(
            venue_id=self.venue.id,
            device_id=self.device.id,
            staff_id=self.staff.id if self.staff else None,
            staff_role=self.staff.role if self.staff else None,
        )


async def load_device(session: AsyncSession, token: str | None) -> Device:
    if not token:
        raise Unauthorized("Device token required")
    device = await session.scalar(select(Device).where(Device.token_hash == token_digest(token)))
    if device is None or not device.is_active:
        # A distinct code: screens forget their setup only on this, never on other errors.
        raise AppError("device_not_set_up", "This screen is not set up (re-paired or disabled)", 401)
    return device


# Screens may always reach these on the cloud, even while their restaurant's hub is in charge.
CLOUD_ALWAYS = ("/v1/devices/me", "/v1/devices/heartbeat")


async def device_ctx(
    request: Request,
    uow: Uow,
    x_device_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> DeviceCtx:
    device = await load_device(uow.session, x_device_token)
    venue = await uow.session.get(Venue, device.venue_id)
    if venue is None:
        raise Unauthorized("Device venue missing")
    if settings.app_mode == "cloud" and hybrid.is_hybrid(venue) and request.url.path not in CLOUD_ALWAYS:
        if await hybrid.hub_in_charge(uow, venue):
            # One writer at a time: while the restaurant's hub is up, its screens work through it.
            raise AppError("use_hub", "This restaurant's hub is running: screens use the hub", 409)
        if request.method != "GET":
            await hybrid.note_takeover(uow, venue)
    ctx = DeviceCtx(device, venue)
    token = _bearer(authorization)
    if token:
        claims = read_jwt(token, "staff")
        if claims.get("device_id") != device.id:
            raise Unauthorized("Staff session belongs to another device")
        staff = await uow.session.get(Staff, claims["sub"])
        if staff is None or not staff.is_active or staff.venue_id != venue.id:
            raise Unauthorized("Staff session is no longer valid")
        ctx.staff = staff
    return ctx


Ctx = Annotated[DeviceCtx, Depends(device_ctx)]


def require_device(*types: str) -> Callable[[DeviceCtx], Awaitable[DeviceCtx]]:
    async def dep(ctx: Ctx) -> DeviceCtx:
        if ctx.device.type not in types:
            raise Forbidden(f"This action needs a {' or '.join(types)} device")
        return ctx

    return dep


def require_staff(*roles: str) -> Callable[[DeviceCtx], Awaitable[DeviceCtx]]:
    """Needs a staff PIN session. Managers and owners can do everything."""

    async def dep(ctx: Ctx) -> DeviceCtx:
        if ctx.staff is None:
            raise Unauthorized("Staff PIN login required")
        allowed = set(roles) | {"manager", "owner"}
        if roles and ctx.staff.role not in allowed:
            raise Forbidden(f"Needs role: {', '.join(sorted(allowed))}")
        return ctx

    return dep


# ------------------------------------------------------------------ admin


@dataclass
class AdminCtx:
    """Who is working in the admin API: a restaurant admin (owner / manager) of one tenant, or one
    of our own team (platform user: installers and support), who can open any venue."""

    admin: AdminUser | None = None
    platform: PlatformUser | None = None

    @property
    def email(self) -> str:
        return self.admin.email if self.admin else self.platform.email if self.platform else ""

    @property
    def is_installer(self) -> bool:
        return self.platform is not None

    def actor(self, venue_id: str) -> Actor:
        if self.platform is not None:
            return Actor(venue_id=venue_id, platform_id=self.platform.id)
        return Actor(venue_id=venue_id, admin_id=self.admin.id if self.admin else None)


async def admin_ctx(uow: Uow, authorization: Annotated[str | None, Header()] = None) -> AdminCtx:
    token = _bearer(authorization)
    if not token:
        raise Unauthorized("Admin login required")
    try:
        claims = read_jwt(token, "admin")
    except Unauthorized:
        # Our installers and support team use their platform login on any venue.
        claims = read_jwt(token, "platform")
        user = await uow.session.get(PlatformUser, claims["sub"])
        if user is None or not user.is_active:
            raise Unauthorized("Platform account disabled") from None
        return AdminCtx(platform=user)
    admin = await uow.session.get(AdminUser, claims["sub"])
    if admin is None or not admin.is_active:
        raise Unauthorized("Admin account disabled")
    return AdminCtx(admin)


Admin = Annotated[AdminCtx, Depends(admin_ctx)]


async def owner_ctx(admin: Admin) -> AdminCtx:
    if not admin.is_installer and (admin.admin is None or admin.admin.role != "owner"):
        raise Forbidden("Only the restaurant owner can do this")
    return admin


Owner = Annotated[AdminCtx, Depends(owner_ctx)]


async def installer_ctx(admin: Admin) -> AdminCtx:
    """Screen, printer and payment setup is done by our team, not by the restaurant."""
    if not admin.is_installer:
        raise Forbidden("Screen, printer and payment setup is done by the installation team")
    return admin


Installer = Annotated[AdminCtx, Depends(installer_ctx)]


# ------------------------------------------------------------------ platform operator


async def platform_ctx(uow: Uow, authorization: Annotated[str | None, Header()] = None) -> PlatformUser:
    token = _bearer(authorization)
    if not token:
        raise Unauthorized("Platform login required")
    claims = read_jwt(token, "platform")
    user = await uow.session.get(PlatformUser, claims["sub"])
    if user is None or not user.is_active:
        raise Unauthorized("Platform account disabled")
    return user


Platform = Annotated[PlatformUser, Depends(platform_ctx)]


async def admin_venue(uow: Uow, admin: Admin, venue_id: Annotated[str, Path()]) -> Venue:
    venue = await uow.session.get(Venue, venue_id)
    if venue is None or (admin.admin is not None and venue.tenant_id != admin.admin.tenant_id):
        raise NotFound("Venue")
    return venue


AdminVenue = Annotated[Venue, Depends(admin_venue)]
