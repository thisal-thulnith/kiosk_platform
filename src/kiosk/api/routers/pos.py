"""The restaurant's own POS (R-BRIDGE): its API (X-Pos-Key) and the installer's setup."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api.deps import Admin, AdminVenue, Uow, installer_ctx
from kiosk.api.routers.admin_org import bump_config
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import Order, PosDelivery, Venue, utcnow
from kiosk.services import payments as pay
from kiosk.services import posbridge
from kiosk.services.menu import effective_menu
from kiosk.services.plans import require_module
from kiosk.services.serializers import order_dict
from kiosk.services.uow import Actor

router = APIRouter(prefix="/v1/pos", tags=["pos bridge"])
admin_router = APIRouter(
    prefix="/v1/admin/venues/{venue_id}/pos", tags=["pos bridge"], dependencies=[Depends(installer_ctx)]
)

PosKey = Annotated[str | None, Header(alias="X-Pos-Key")]


async def _venue(uow: Uow, key: str | None) -> Venue:
    venue = await posbridge.venue_for_key(uow, key)
    require_module(venue, "R-BRIDGE")
    return venue


async def _order(uow: Uow, venue: Venue, order_id: str) -> Order:
    order = await uow.session.get(Order, order_id)
    if order is None or order.venue_id != venue.id:
        raise NotFound("Order")
    return order


# ------------------------------------------------------------------ the POS calls these


@router.get("/orders")
async def pos_orders(uow: Uow, key: PosKey = None, since: datetime | None = None) -> dict[str, Any]:
    """Orders changed since a time (oldest first, at most 200). Poll with the last updated_at."""
    venue = await _venue(uow, key)
    q = select(Order).where(Order.venue_id == venue.id)
    if since:
        q = q.where(Order.updated_at > since)
    rows = (await uow.session.scalars(q.order_by(Order.updated_at).limit(200))).all()
    out = []
    for o in rows:
        out.append(posbridge.pos_order(o, await posbridge._codes(uow.session, o)))
    return {"orders": out, "server_time": utcnow().isoformat()}


@router.get("/orders/{order_id}")
async def pos_order(order_id: str, uow: Uow, key: PosKey = None) -> dict[str, Any]:
    venue = await _venue(uow, key)
    o = await _order(uow, venue, order_id)
    return posbridge.pos_order(o, await posbridge._codes(uow.session, o))


class PaidIn(BaseModel):
    reference: str = Field(min_length=1, max_length=60, description="The POS's receipt / transaction number")
    method: str = Field("pos", max_length=20, description="What the POS took: cash, card...")
    amount: int | None = Field(None, ge=1, description="LKR cents; empty = what is left to pay")


@router.post("/orders/{order_id}/paid")
async def pos_paid(order_id: str, body: PaidIn, uow: Uow, key: PosKey = None) -> dict[str, Any]:
    """The guest paid at the POS: the kitchen starts, the receipt prints, points are earned."""
    venue = await _venue(uow, key)
    order = await _order(uow, venue, order_id)
    if any(
        p.method == "pos" and p.external_ref and p.external_ref.endswith(f":{body.reference}")
        for p in order.payments
    ):
        return order_dict(order)  # same POS receipt sent twice: already recorded
    await pay.pay_by_pos(uow, venue, order, body.reference, body.method, body.amount)
    await uow.commit()
    return order_dict(order)


@router.get("/menu")
async def pos_menu(uow: Uow, key: PosKey = None) -> dict[str, Any]:
    venue = await _venue(uow, key)
    return await effective_menu(uow.session, venue, utcnow())


class MenuRow(BaseModel):
    plu: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    price: int = Field(ge=0, description="LKR cents")
    category: str | None = None
    station: str | None = None
    available: bool | None = None


class MenuIn(BaseModel):
    items: list[MenuRow] = Field(max_length=2000)


@router.put("/menu")
async def pos_menu_push(body: MenuIn, uow: Uow, key: PosKey = None) -> dict[str, Any]:
    """The POS sends its menu. Matched by PLU; prices, names and availability follow the POS."""
    venue = await _venue(uow, key)
    result = await posbridge.import_menu(
        uow, venue, [r.model_dump(exclude_none=True) for r in body.items], Actor(venue_id=venue.id)
    )
    await uow.commit()
    return result


# ------------------------------------------------------------------ installer setup


class LinkIn(BaseModel):
    pos_name: str | None = Field(None, max_length=80)
    url: str | None = Field(None, max_length=500)
    secret: str | None = Field(None, max_length=200)
    events: list[str] | None = None
    menu_from_pos: bool | None = None
    is_active: bool | None = None


@admin_router.get("")
async def get_link(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    return posbridge.link_dict(await posbridge.link_for(uow, venue.id))


@admin_router.put("")
async def put_link(body: LinkIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    require_module(venue, "R-BRIDGE")
    link = await posbridge.save_link(uow, venue, admin.actor(venue.id), body.model_dump())
    await uow.commit()
    return posbridge.link_dict(link)


@admin_router.post("/key")
async def make_key(venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    """A key for the POS to call our API. Shown once; a new key replaces the old one."""
    require_module(venue, "R-BRIDGE")
    key = await posbridge.new_key(uow, venue, admin.actor(venue.id))
    await uow.commit()
    return {"key": key}


@admin_router.post("/test")
async def test_link(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """Send a signed test event to the POS now and report what it answered."""
    link = await posbridge.link_for(uow, venue.id)
    if link is None or not link.url:
        raise AppError("not_set_up", "Enter the POS address first")
    d = PosDelivery(
        venue_id=venue.id,
        event="test",
        payload={"event": "test", "venue": venue.code},
        status="queued",
        attempts=0,
    )
    uow.session.add(d)
    await uow.commit()
    await posbridge.deliver(d.id)
    await uow.session.refresh(d)
    await uow.session.refresh(link)
    return {"ok": d.status == "sent", "response_code": d.response_code, "error": d.error}


@admin_router.get("/deliveries")
async def deliveries(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(PosDelivery)
            .where(PosDelivery.venue_id == venue.id)
            .order_by(PosDelivery.created_at.desc())
            .limit(30)
        )
    ).all()
    return [
        {
            "id": d.id,
            "event": d.event,
            "order_id": d.order_id,
            "token": (d.payload.get("order") or {}).get("token"),
            "status": d.status,
            "attempts": d.attempts,
            "response_code": d.response_code,
            "error": d.error,
            "at": d.created_at.isoformat(),
        }
        for d in rows
    ]


@admin_router.post("/menu-import")
async def menu_import(body: MenuIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    """Import the POS's menu from its export (CSV turned into rows by the Setup console)."""
    require_module(venue, "R-BRIDGE")
    result = await posbridge.import_menu(
        uow, venue, [r.model_dump(exclude_none=True) for r in body.items], admin.actor(venue.id)
    )
    bump_config(venue)
    await uow.commit()
    return result
