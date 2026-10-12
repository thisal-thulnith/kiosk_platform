"""Platform operator API: create restaurants (tenants) and see all of them.

Each restaurant gets its own owner login. Everything a restaurant owns is reached through its
tenant, so one restaurant's admins never see another's venues, menus, screens or orders.
"""

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from kiosk.api import limits
from kiosk.api.deps import Platform, Uow
from kiosk.auth.security import hash_secret, verify_secret
from kiosk.domain.modules import PlanError, build_plan, catalog
from kiosk.errors import AppError, Conflict, Unauthorized
from kiosk.infra.models import AdminUser, AuditLog, Device, PlatformUser, PriceBook, Staff, Tenant, Venue
from kiosk.realtime.hub import hub
from kiosk.seed import add_sample_menu
from kiosk.services import logins
from kiosk.services.plans import create_slots, make_quote, price_book, usage
from kiosk.services.setup import checklist as setup_checklist

router = APIRouter(prefix="/v1/platform", tags=["platform"])


class Login(BaseModel):
    email: str
    password: str
    otp: str | None = None


@router.post("/auth/login")
async def login(body: Login, request: Request, uow: Uow) -> dict[str, Any]:
    """Our team only (older clients). Same rules as /v1/auth/login, the phone code included."""
    limits.check(request, "login")
    user = await uow.session.scalar(select(PlatformUser).where(PlatformUser.email == body.email.lower()))
    if user is None or not user.is_active or not verify_secret(body.password, user.password_hash):
        limits.failed(request, "login")
        raise Unauthorized("Wrong email or password")
    return await logins.team_login(uow, request, user, body.otp)


async def _tenant_summary(uow: Uow, tenant: Tenant) -> dict[str, Any]:
    venues = (
        await uow.session.scalars(select(Venue).where(Venue.tenant_id == tenant.id).order_by(Venue.name))
    ).all()
    admins = (
        await uow.session.scalars(
            select(AdminUser).where(AdminUser.tenant_id == tenant.id).order_by(AdminUser.email)
        )
    ).all()
    out_venues = []
    for v in venues:
        devices = await uow.session.scalar(
            select(func.count()).select_from(Device).where(Device.venue_id == v.id, Device.is_active)
        )
        check = await setup_checklist(uow, v)
        out_venues.append(
            {
                "id": v.id,
                "name": v.name,
                "code": v.code,
                "timezone": v.timezone,
                "screens": int(devices or 0),
                "screens_online": len(hub.connected_devices(v.id)),
                "plan": v.plan or None,
                # How far the installation is (go-live checklist), for the restaurant list.
                "setup": {k: check[k] for k in ("done", "total", "ready")},
            }
        )
    return {
        "id": tenant.id,
        "name": tenant.name,
        "created_at": tenant.created_at.isoformat(),
        "venues": out_venues,
        "admins": [{"email": a.email, "role": a.role, "is_active": a.is_active} for a in admins],
    }


@router.get("/tenants")
async def list_tenants(_: Platform, uow: Uow) -> list[dict[str, Any]]:
    tenants = (await uow.session.scalars(select(Tenant).order_by(Tenant.name))).all()
    return [await _tenant_summary(uow, t) for t in tenants]


class PlanIn(BaseModel):
    pack: str = Field(description="pack1 | pack2 | pack3 | custom | hotel")
    tier: str | None = Field(default=None, description="starter | standard | premium (packs 1-3)")
    add: list[str] = Field(default_factory=list, description="Add-on modules for the tier")
    screens: dict[str, int] = Field(default_factory=dict, description="Extra screens on top of the tier")
    modules: list[str] = Field(default_factory=list, description="Custom / hotel: the modules")
    hardware: dict[str, int] = Field(
        default_factory=dict,
        description="Equipment: router, receipt_printer, cash_drawer, kiosk_printer, kitchen_printer, "
        "card_reader, scanner, hub, ups. Anything the screens need is added automatically",
    )
    flows: list[str] = Field(
        default_factory=list,
        description="How the restaurant works: kiosk_self_order, table_order, table_tab, counter_pos, "
        "waiter_service, existing_pos, status_display, menu_board, kitchen_printing, offline_hybrid, "
        "guest_sms",
    )


class RestaurantIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200, description="Legal or brand name")
    venue_name: str = Field(min_length=2, max_length=200, description="First branch, e.g. 'Colombo 03'")
    venue_code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    timezone: str = "Asia/Colombo"
    owner_email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    owner_password: str = Field(min_length=8, max_length=128)
    manager_pin: str | None = Field(
        default=None,
        min_length=4,
        max_length=8,
        pattern=r"^\d+$",
        description="PIN for a first 'Manager' staff",
    )
    sample_menu: bool = Field(default=False, description="Start with the demo menu and SC/VAT rules")
    plan: PlanIn | None = Field(default=None, description="Package; screen slots are created from it")


def _plan(body: PlanIn) -> dict[str, Any]:
    try:
        return build_plan(
            body.pack, body.tier, body.add, body.screens, body.modules, body.hardware, body.flows
        )
    except PlanError as exc:
        raise AppError(exc.code, str(exc)) from exc


def apply_flow_settings(venue: Venue) -> None:
    """The chosen flows set how the restaurant works (release rule, tabs, waiter service, hybrid...)."""
    flow_settings = (venue.plan or {}).get("settings") or {}
    if flow_settings:
        venue.settings = {**(venue.settings or {}), **flow_settings}


def check_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AppError("bad_timezone", f"Unknown timezone {name}") from exc


async def create_venue(
    uow: Uow, tenant: Tenant, name: str, code: str, timezone: str, sample_menu: bool
) -> Venue:
    code = code.upper()
    if await uow.session.scalar(select(Venue.id).where(Venue.code == code)):
        raise Conflict("venue_code_taken", f"Venue code {code} is already used")
    venue = Venue(tenant_id=tenant.id, name=name, code=code, timezone=timezone)
    uow.session.add(venue)
    await uow.session.flush()
    if sample_menu:
        await add_sample_menu(uow.session, venue)
    return venue


@router.post("/tenants", status_code=201)
async def create_restaurant(body: RestaurantIn, user: Platform, uow: Uow) -> dict[str, Any]:
    """Create a restaurant: tenant + first branch + owner login (+ optional manager PIN and sample menu)."""
    email = body.owner_email.lower()
    if await uow.session.scalar(select(AdminUser.id).where(AdminUser.email == email)):
        raise Conflict("email_taken", "An admin with this email already exists")
    check_timezone(body.timezone)
    tenant = Tenant(name=body.company_name)
    uow.session.add(tenant)
    await uow.session.flush()
    venue = await create_venue(uow, tenant, body.venue_name, body.venue_code, body.timezone, body.sample_menu)
    uow.session.add(
        AdminUser(tenant_id=tenant.id, email=email, password_hash=hash_secret(body.owner_password))
    )
    if body.manager_pin:
        uow.session.add(
            Staff(venue_id=venue.id, name="Manager", role="manager", pin_hash=hash_secret(body.manager_pin))
        )
    if body.plan:
        venue.plan = _plan(body.plan)
        apply_flow_settings(venue)
        await create_slots(uow, venue)
    await uow.session.flush()
    # Audited against the new venue, so the owner can see who set the restaurant up.
    uow.session.add(
        AuditLog(
            venue_id=venue.id, action="platform.tenant_created", target=tenant.id, data={"by": user.email}
        )
    )
    await uow.commit()
    return await _tenant_summary(uow, tenant)


# ------------------------------------------------------------------ packages, prices, quotes


@router.get("/catalog")
async def get_catalog(_: Platform) -> dict[str, Any]:
    """Modules (R-*, H-*) and the Pack 1/2/3 tiers with their screens and add-ons."""
    return catalog()


@router.post("/quote")
async def get_quote(body: PlanIn, _: Platform, uow: Uow) -> dict[str, Any]:
    plan = _plan(body)
    return {"plan": plan, **(await make_quote(uow, plan))}


class PriceIn(BaseModel):
    item: str = Field(pattern=r"^(module|screen):[A-Za-z-]+$")
    monthly: int = Field(ge=0, description="LKR cents per month")
    once: int = Field(ge=0, description="LKR cents one-time (hardware, setup)")


@router.get("/prices")
async def get_prices(_: Platform, uow: Uow) -> dict[str, dict[str, int]]:
    return await price_book(uow)


@router.put("/prices")
async def put_prices(body: list[PriceIn], user: Platform, uow: Uow) -> dict[str, dict[str, int]]:
    for p in body:
        row = await uow.session.get(PriceBook, p.item)
        if row is None:
            uow.session.add(PriceBook(item=p.item, monthly=p.monthly, once=p.once))
        else:
            row.monthly, row.once = p.monthly, p.once
    await uow.commit()
    return await price_book(uow)


class VenuePlanIn(PlanIn):
    create_slots: bool = Field(
        default=True, description="Create missing screen slots (Table T1..Tn, Kitchen 1...)"
    )


@router.put("/venues/{venue_id}/plan")
async def set_plan(venue_id: str, body: VenuePlanIn, user: Platform, uow: Uow) -> dict[str, Any]:
    venue = await uow.session.get(Venue, venue_id)
    if venue is None:
        raise AppError("not_found", "Venue not found", 404)
    plan = _plan(body)
    venue.plan = plan
    apply_flow_settings(venue)
    made = await create_slots(uow, venue) if body.create_slots else []
    venue.config_version += 1
    uow.session.add(
        AuditLog(
            venue_id=venue.id, action="platform.plan_set", target=venue.id, data={"by": user.email, **plan}
        )
    )
    await uow.commit()
    return {"plan": plan, "slots_created": [d.name for d in made], "usage": await usage(uow, venue)}
