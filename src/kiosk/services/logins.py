"""One login for everyone who manages restaurants. The account decides where it goes:
- our team (platform users): the Platform console. A phone code (2-step) is needed in prod; the
  first login sets it up from a QR code.
- a restaurant's owner or manager (admin users): their Owner app, own restaurants only.
"""

from typing import Any

from fastapi import Request
from sqlalchemy import select

from kiosk.api import limits
from kiosk.auth import totp
from kiosk.auth.security import issue_jwt, read_jwt, verify_secret
from kiosk.config import settings
from kiosk.errors import Unauthorized
from kiosk.infra.models import AdminUser, PlatformUser
from kiosk.infra.secrets import decrypt, encrypt
from kiosk.services.uow import UnitOfWork


def team_allowed_here(request: Request) -> bool:
    """Our team logs in only on the admin address, when there is one."""
    return not settings.admin_host or request.url.hostname == settings.admin_host


def _wrong(request: Request, message: str = "Wrong email or password") -> Unauthorized:
    limits.failed(request, "login")
    return Unauthorized(message)


def _team_token(user: PlatformUser) -> dict[str, Any]:
    token = issue_jwt({"sub": user.id, "typ": "platform"}, settings.admin_session_hours)
    return {
        "access_token": token,
        "token_type": "bearer",
        "kind": "installer",
        "name": user.name,
        "email": user.email,
        "two_step": bool(user.totp_secret_enc),
    }


def _owner_token(admin: AdminUser) -> dict[str, Any]:
    token = issue_jwt(
        {"sub": admin.id, "typ": "admin", "tenant_id": admin.tenant_id, "role": admin.role},
        settings.admin_session_hours,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "kind": "admin",
        "tenant_id": admin.tenant_id,
        "role": admin.role,
    }


async def team_login(
    uow: UnitOfWork, request: Request, user: PlatformUser, otp: str | None
) -> dict[str, Any]:
    """Password already checked. With 2-step on: the phone code, or (first time) its setup."""
    secret = decrypt(user.totp_secret_enc) if user.totp_secret_enc else None
    if secret:
        if not otp:
            return {"need": "otp"}
        step = totp.verify(secret, otp, user.totp_last_step)
        if step is None:
            raise _wrong(request, "Wrong code. Type the newest code from your authenticator app")
        user.totp_last_step = step
        await uow.commit()
        return _team_token(user)
    if settings.team_2fa_required:
        new = totp.new_secret()
        claims = {"sub": user.id, "typ": "totp_setup", "secret": new}
        return {
            "need": "setup",
            "setup_token": issue_jwt(claims, 1),  # an hour to scan and type the first code
            "secret": new,
            "uri": totp.setup_uri(new, user.email, settings.product_name),
        }
    return _team_token(user)


async def login(
    uow: UnitOfWork, request: Request, email: str, password: str, otp: str | None
) -> dict[str, Any]:
    limits.check(request, "login")
    email = email.strip().lower()
    if team_allowed_here(request):
        user = await uow.session.scalar(select(PlatformUser).where(PlatformUser.email == email))
        if user is not None:
            if not user.is_active or not verify_secret(password, user.password_hash):
                raise _wrong(request)
            return await team_login(uow, request, user, otp)
    admin = await uow.session.scalar(select(AdminUser).where(AdminUser.email == email))
    if admin is None or not admin.is_active or not verify_secret(password, admin.password_hash):
        raise _wrong(request)
    return _owner_token(admin)


async def finish_setup(uow: UnitOfWork, request: Request, setup_token: str, otp: str) -> dict[str, Any]:
    """The first code from the newly added account proves the phone has it: 2-step is on."""
    limits.check(request, "login")
    claims = read_jwt(setup_token, "totp_setup")
    user = await uow.session.get(PlatformUser, claims["sub"])
    if user is None or not user.is_active:
        raise _wrong(request, "Log in again")
    step = totp.verify(claims["secret"], otp)
    if step is None:
        raise _wrong(request, "Wrong code. Type the code your authenticator app shows now")
    user.totp_secret_enc = encrypt(claims["secret"])
    user.totp_last_step = step
    await uow.commit()
    return _team_token(user)
