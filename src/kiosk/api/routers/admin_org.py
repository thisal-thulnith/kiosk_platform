import re
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api.deps import Admin, AdminVenue, Installer, Owner, Uow
from kiosk.auth.security import hash_secret, new_pairing_code, new_token, token_digest
from kiosk.domain.modules import has_module
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import (
    DEFAULT_VENUE_SETTINGS,
    AiAction,
    AuditLog,
    Device,
    MenuCategory,
    Staff,
    Tenant,
    Venue,
    utcnow,
)
from kiosk.realtime.hub import hub
from kiosk.services import screen_codes
from kiosk.services.payments import ASSISTED_DEVICES, ATTENDED_DEVICES
from kiosk.services.plans import check_screen_limit, usage
from kiosk.services.serializers import staff_dict

router = APIRouter(prefix="/v1/admin/venues/{venue_id}", tags=["admin"])


def bump_config(venue: Venue) -> None:
    venue.config_version += 1


def venue_dict(v: Venue) -> dict[str, Any]:
    return {
        "id": v.id,
        "name": v.name,
        "code": v.code,
        "timezone": v.timezone,
        "settings": {**DEFAULT_VENUE_SETTINGS, **(v.settings or {})},
        "config_version": v.config_version,
        "plan": v.plan or None,  # modules and screens the restaurant bought (screens hide the rest)
    }


venues_router = APIRouter(prefix="/v1/admin/venues", tags=["admin"])


@venues_router.get("")
async def list_venues(admin: Admin, uow: Uow) -> list[dict[str, Any]]:
    """Venues of the logged-in admin's tenant; every venue for our installers."""
    q = select(Venue).order_by(Venue.name)
    if admin.admin is not None:
        q = q.where(Venue.tenant_id == admin.admin.tenant_id)
    rows = (await uow.session.scalars(q)).all()
    if admin.admin is not None:
        return [venue_dict(v) for v in rows]
    tenants = {t.id: t.name for t in (await uow.session.scalars(select(Tenant))).all()}
    return [{**venue_dict(v), "tenant_name": tenants.get(v.tenant_id)} for v in rows]


class VenueIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    timezone: str = "Asia/Colombo"
    sample_menu: bool = False
    same_restaurant_as: str | None = Field(None, description="Installers: a venue of the restaurant")


@venues_router.post("", status_code=201)
async def create_branch(body: VenueIn, owner: Owner, uow: Uow) -> dict[str, Any]:
    """Owner adds a branch to their own restaurant."""
    from kiosk.api.routers.platform import check_timezone, create_venue

    check_timezone(body.timezone)
    if owner.admin is not None:
        tenant = await uow.session.get(Tenant, owner.admin.tenant_id)
    else:  # our installer adds a branch next to a venue of that restaurant
        sibling = await uow.session.get(Venue, body.same_restaurant_as or "")
        if sibling is None:
            raise AppError("restaurant_required", "Say which restaurant the branch belongs to")
        tenant = await uow.session.get(Tenant, sibling.tenant_id)
    assert tenant is not None
    venue = await create_venue(uow, tenant, body.name, body.code, body.timezone, body.sample_menu)
    uow.audit(owner.actor(venue.id), "venue.create", venue.id, name=body.name)
    await uow.commit()
    return venue_dict(venue)


@router.get("")
async def get_venue(venue: AdminVenue) -> dict[str, Any]:
    return venue_dict(venue)


@router.get("/plan")
async def get_plan(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """The package this venue bought, and how many screens of each type are in use."""
    return {"plan": venue.plan or None, "usage": await usage(uow, venue)}


class VenuePatch(BaseModel):
    name: str | None = None
    timezone: str | None = None
    settings: dict[str, Any] | None = None


@router.patch("")
async def patch_venue(body: VenuePatch, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    if body.name:
        venue.name = body.name
    if body.timezone:
        venue.timezone = body.timezone
    if body.settings:
        unknown = set(body.settings) - set(DEFAULT_VENUE_SETTINGS)
        if unknown:
            raise AppError("unknown_setting", f"Unknown settings: {', '.join(sorted(unknown))}")
        if body.settings.get("table_access", "open") not in ("open", "staff_opens"):
            raise AppError("bad_setting", "table_access must be open or staff_opens")
        if body.settings.get("release_rule", "A") not in ("A", "B"):
            raise AppError("bad_setting", "release_rule must be A or B")
        if body.settings.get("dine_in_mode", "pay_first") not in ("pay_first", "tab"):
            raise AppError("bad_setting", "dine_in_mode must be pay_first or tab")
        if body.settings.get("serve_mode", "self_pickup") not in ("self_pickup", "waiter"):
            raise AppError("bad_setting", "serve_mode must be self_pickup or waiter")
        if body.settings.get("mode", "manual") not in ("manual", "ai"):
            raise AppError("bad_setting", "mode must be manual or ai")
        if "ai_level" in body.settings and body.settings["ai_level"] not in (0, 1, 2, 3, 4):
            raise AppError("bad_setting", "ai_level must be 0-4")
        if body.settings.get("ai_level") == 4 and not has_module(venue.plan, "R-INV"):
            raise AppError("bad_setting", "AI level 4 (deal prices) needs the Inventory module (R-INV)")
        cap = body.settings.get("ai_price_cap_bp")
        if cap is not None and (not isinstance(cap, int) or not 0 <= cap <= 5000):
            raise AppError("bad_setting", "ai_price_cap_bp must be 0-5000 (at most 50% off)")
        color = body.settings.get("brand_color")
        if color is not None and not (isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
            raise AppError("bad_setting", "brand_color must look like #f5a524")
        logo = body.settings.get("logo_url")
        if logo is not None and not (
            isinstance(logo, str) and (logo == "" or logo.startswith(("/media/", "https://")))
        ):
            raise AppError(
                "bad_setting", "logo_url must be an uploaded photo (/media/...) or an https address"
            )
        if body.settings.get("theme", "light") not in ("light", "dark"):
            raise AppError("bad_setting", "theme must be light or dark")
        venue.settings = {**(venue.settings or {}), **body.settings}
    bump_config(venue)
    uow.audit(admin.actor(venue.id), "venue.update", venue.id, **body.model_dump(exclude_none=True))
    if body.settings and {"mode", "ai_level"} & set(body.settings):
        uow.session.add(
            AiAction(
                venue_id=venue.id,
                kind="mode",
                data={"mode": venue.setting("mode"), "ai_level": venue.setting("ai_level")},
                reason=f"Set by {admin.email}",
            )
        )
    # Screens reload settings (mode, languages, payment rules) without a restart.
    uow.emit(
        venue.id,
        "venue.settings",
        {"settings": {**DEFAULT_VENUE_SETTINGS, **venue.settings}},
        ["menu", "status"],
    )
    await uow.commit()
    return venue_dict(venue)


# ------------------------------------------------------------------ staff

StaffRole = Literal["cashier", "waiter", "kitchen", "manager", "owner"]


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: StaffRole
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class StaffPatch(BaseModel):
    name: str | None = None
    role: StaffRole | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=8, pattern=r"^\d+$")
    is_active: bool | None = None


@router.get("/staff")
async def list_staff(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (await uow.session.scalars(select(Staff).where(Staff.venue_id == venue.id))).all()
    return [staff_dict(s) for s in rows]


@router.post("/staff", status_code=201)
async def create_staff(body: StaffIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    staff = Staff(venue_id=venue.id, name=body.name, role=body.role, pin_hash=hash_secret(body.pin))
    uow.session.add(staff)
    bump_config(venue)
    await uow.session.flush()
    uow.audit(admin.actor(venue.id), "staff.create", staff.id, role=body.role)
    await uow.commit()
    return staff_dict(staff)


@router.patch("/staff/{staff_id}")
async def update_staff(
    staff_id: str, body: StaffPatch, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    staff = await uow.session.get(Staff, staff_id)
    if staff is None or staff.venue_id != venue.id:
        raise NotFound("Staff")
    if body.name is not None:
        staff.name = body.name
    if body.role is not None:
        staff.role = body.role
    if body.pin is not None:
        staff.pin_hash = hash_secret(body.pin)
        staff.failed_pin_attempts = 0
        staff.locked_until = None
    if body.is_active is not None:
        staff.is_active = body.is_active
    bump_config(venue)
    uow.audit(
        admin.actor(venue.id),
        "staff.update",
        staff.id,
        **body.model_dump(exclude_none=True, exclude={"pin"}),
        pin_changed=body.pin is not None,
    )
    await uow.commit()
    return staff_dict(staff)


# ------------------------------------------------------------------ devices

DeviceType = Literal["cashier", "kds", "status", "kiosk", "table", "waiter", "board"]


class DeviceIn(BaseModel):
    type: DeviceType
    name: str = Field(min_length=1, max_length=120)
    station: str | None = None
    table_ref: str | None = None


def device_dict(d: Device, online: set[str] | None = None) -> dict[str, Any]:
    return {
        "id": d.id,
        "type": d.type,
        "name": d.name,
        "station": d.station,
        "table_ref": d.table_ref,
        "paired": d.token_hash is not None,
        "is_active": d.is_active,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "connected": d.id in (online or set()),
        "card": (d.settings or {}).get("card"),
        "hardware": (d.settings or {}).get("hardware"),
        "menu_categories": ((d.settings or {}).get("menu") or {}).get("categories") or [],
        # The physical tablet: model, system, browser / app, screen, address, install id.
        "client": (d.settings or {}).get("client"),
        # Sign-in: the restaurant's address + this code (like a Square device code).
        "screen_code": screen_codes.shown(d),
    }


@router.get("/devices")
async def list_devices(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (await uow.session.scalars(select(Device).where(Device.venue_id == venue.id))).all()
    if missing := [row for row in rows if not row.code_enc]:  # made before screen codes existed
        for row in missing:
            screen_codes.new_code(row)
        await uow.commit()
    online = hub.connected_devices(venue.id)
    out = [device_dict(d, online) for d in rows]
    # One tablet set up as two screens (e.g. re-used without unpairing the old one): say so.
    by_install: dict[str, list[str]] = {}
    for d in out:
        iid = (d["client"] or {}).get("install_id")
        if iid and d["paired"]:
            by_install.setdefault(iid, []).append(d["name"])
    for d in out:
        iid = (d["client"] or {}).get("install_id")
        d["same_tablet_as"] = [n for n in by_install.get(iid or "", []) if n != d["name"]]
    return out


@router.post("/devices", status_code=201)
async def create_device(body: DeviceIn, venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    """Register a device and get a pairing code to type into it (valid 10 minutes)."""
    if body.type == "table" and not body.table_ref:
        raise AppError("table_ref_required", "Table devices need a table_ref")
    await check_screen_limit(uow, venue, body.type)
    device = Device(
        venue_id=venue.id, type=body.type, name=body.name, station=body.station, table_ref=body.table_ref
    )
    code = await _unique_code(uow)
    device.pairing_code = code
    device.pairing_expires_at = utcnow() + timedelta(minutes=10)
    screen_codes.new_code(device)
    uow.session.add(device)
    await uow.session.flush()
    uow.audit(admin.actor(venue.id), "device.create", device.id, type=body.type)
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return {
        **device_dict(device),
        "pairing_code": code,
        "pairing_expires_at": device.pairing_expires_at.isoformat(),
    }


class SetupHereIn(BaseModel):
    """Either take over an existing screen slot (device_id), or create a new one."""

    device_id: str | None = None
    type: DeviceType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    station: str | None = None
    table_ref: str | None = None


@router.post("/devices/setup-here")
async def setup_here(body: SetupHereIn, venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    """Set up the screen the owner or manager is logged in on, with their password instead of a code.

    Returns the device token once; the screen keeps it and never needs setting up again. Taking over
    an existing slot (e.g. a replacement tablet for Table 5) stops the old screen's token.
    """
    if body.device_id:
        device = await uow.session.get(Device, body.device_id)
        if device is None or device.venue_id != venue.id:
            raise NotFound("Device")
        if not device.is_active:
            raise AppError("device_disabled", "This screen is disabled. Enable it in the Setup console first")
    else:
        if body.type is None or not body.name:
            raise AppError("type_required", "Choose a screen type and name, or an existing screen")
        if body.type == "table" and not body.table_ref:
            raise AppError("table_ref_required", "Table screens need a table number")
        await check_screen_limit(uow, venue, body.type)
        device = Device(
            venue_id=venue.id,
            type=body.type,
            name=body.name,
            station=body.station or None,
            table_ref=body.table_ref,
        )
        uow.session.add(device)
    token = new_token()
    device.token_hash = token_digest(token)
    device.pairing_code = None
    device.pairing_expires_at = None
    device.last_seen_at = utcnow()
    await uow.session.flush()
    uow.audit(admin.actor(venue.id), "device.setup_here", device.id, type=device.type, by=admin.email)
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return {"device_token": token, "device": device_dict(device)}


@router.post("/devices/{device_id}/pairing-code")
async def repair_device(device_id: str, venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    """New pairing code. The old device token stops working immediately."""
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    device.token_hash = None
    device.pairing_code = await _unique_code(uow)
    device.pairing_expires_at = utcnow() + timedelta(minutes=10)
    uow.audit(admin.actor(venue.id), "device.repair", device.id)
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return {
        **device_dict(device),
        "pairing_code": device.pairing_code,
        "pairing_expires_at": device.pairing_expires_at.isoformat(),
    }


@router.post("/devices/{device_id}/screen-code")
async def reset_screen_code(device_id: str, venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    """A new screen code. The old code stops working and the device on this screen is signed out."""
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    code = screen_codes.new_code(device)
    device.token_hash = None
    uow.audit(admin.actor(venue.id), "device.code_reset", device.id)
    bump_config(venue)
    await uow.commit()
    return {**device_dict(device), "screen_code": code}


class DevicePatch(BaseModel):
    name: str | None = None
    station: str | None = None
    table_ref: str | None = None
    is_active: bool | None = None
    card_mode: Literal["none", "reader", "softpos"] | None = Field(
        default=None,
        description="reader: built-in terminal (needs card_terminal_id). softpos: tap on staff tablet",
    )
    card_terminal_id: str | None = Field(
        default=None, max_length=80, description="Reader serial / processor id"
    )
    menu_categories: list[str] | None = Field(
        default=None, description="Guest screens: show only these category ids ([] = all)"
    )


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: str, body: DevicePatch, venue: AdminVenue, admin: Installer, uow: Uow
) -> dict[str, Any]:
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_active") and not device.is_active:
        await check_screen_limit(uow, venue, device.type)
    categories = changes.pop("menu_categories", None)
    if categories is not None:
        found = set(
            (
                await uow.session.scalars(
                    select(MenuCategory.id).where(
                        MenuCategory.venue_id == venue.id, MenuCategory.id.in_(categories)
                    )
                )
            ).all()
        )
        if set(categories) - found:
            raise AppError("bad_category", "Unknown category for this venue")
        device.settings = {**(device.settings or {}), "menu": {"categories": categories}}
    mode = changes.pop("card_mode", None)
    terminal_id = changes.pop("card_terminal_id", None)
    if mode is not None:
        settings = dict(device.settings or {})
        if mode == "none":
            settings.pop("card", None)
        elif mode == "softpos":
            if device.type not in (*ATTENDED_DEVICES, *ASSISTED_DEVICES):
                raise AppError(
                    "softpos_attended_only",
                    "Tap-on-tablet (SoftPOS) is only allowed on staff screens. Use a built-in reader here",
                )
            settings["card"] = {"mode": "softpos"}
        else:
            if not terminal_id:
                raise AppError("terminal_id_required", "Enter the card reader's serial / terminal id")
            settings["card"] = {"mode": "reader", "terminal_id": terminal_id}
        device.settings = settings
    for field, value in changes.items():
        setattr(device, field, value)
    uow.audit(admin.actor(venue.id), "device.update", device.id, **body.model_dump(exclude_unset=True))
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return device_dict(device)


class CommandIn(BaseModel):
    command: Literal["reload", "identify", "connect_printer"]


@router.post("/devices/{device_id}/command")
async def device_command(
    device_id: str, body: CommandIn, venue: AdminVenue, admin: Installer, uow: Uow
) -> dict[str, Any]:
    """Remote control: reload a screen (picks up new software and settings) or make it show its name."""
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    online = device.id in hub.connected_devices(venue.id)
    uow.emit(
        venue.id, "device.command", {"device_id": device.id, "command": body.command}, [f"device:{device.id}"]
    )
    uow.audit(admin.actor(venue.id), f"device.{body.command}", device.id)
    await uow.commit()
    return {"sent": online, "device_id": device.id, "command": body.command}


async def _unique_code(uow: Uow) -> str:
    for _ in range(20):
        code = new_pairing_code()
        taken = await uow.session.scalar(select(Device.id).where(Device.pairing_code == code))
        if not taken:
            return code
    raise AppError("pairing_unavailable", "Could not create a pairing code, try again", 503)


# ------------------------------------------------------------------ audit


@router.get("/audit")
async def audit_log(venue: AdminVenue, uow: Uow, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(AuditLog)
            .where(AuditLog.venue_id == venue.id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 500))
        )
    ).all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "target": a.target,
            "data": a.data,
            "device_id": a.device_id,
            "staff_id": a.staff_id,
            "admin_id": a.admin_id,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]
