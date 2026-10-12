"""Loyalty: guest screens look up or join by phone (with consent); staff and owners manage members."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from kiosk.api.deps import AdminVenue, Ctx, Uow
from kiosk.domain.orders import PaymentStatus, Status
from kiosk.errors import AppError, Conflict, NotFound
from kiosk.infra.models import Customer, Order
from kiosk.services import loyalty
from kiosk.services import orders as order_svc
from kiosk.services.serializers import order_dict

router = APIRouter(prefix="/v1", tags=["loyalty"])


class PhoneIn(BaseModel):
    phone: str = Field(min_length=7, max_length=20)


class JoinIn(PhoneIn):
    name: str | None = Field(default=None, max_length=120)
    consent: bool = Field(description="The guest agreed to the member terms shown on screen")


@router.post("/loyalty/lookup")
async def lookup(body: PhoneIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    customer = await loyalty.find(uow, ctx.venue, body.phone)
    if customer is None or customer.forgotten_at or not customer.consent_at:
        return {"known": False, "consent_text": ctx.venue.setting("loyalty_consent_text")}
    return await loyalty.summary(uow, ctx.venue, customer)


@router.post("/loyalty/join", status_code=201)
async def join(body: JoinIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    customer = await loyalty.join(uow, ctx.venue, body.phone, body.name, body.consent)
    await uow.commit()
    return await loyalty.summary(uow, ctx.venue, customer)


@router.post("/orders/{order_id}/customer")
async def attach(order_id: str, body: PhoneIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Add a member to an unpaid order: points on payment, and their tier discount now."""
    order = await order_svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    if ctx.staff is None and order.device_id != ctx.device.id:
        raise AppError("forbidden", "Only the screen that placed this order, or staff, can change it", 403)
    if (
        order.status not in (Status.PLACED, Status.IN_KITCHEN, Status.READY)
        or order.payment_status != PaymentStatus.UNPAID
    ):
        raise Conflict("order_locked", "Members can be added before payment starts")
    customer = await loyalty.find(uow, ctx.venue, body.phone)
    if customer is None or customer.forgotten_at or not customer.consent_at:
        raise NotFound("Member")
    order.customer_id = customer.id
    discount = loyalty.discount_for(ctx.venue, customer)
    order.discount_bp = discount.bp if discount else 0
    order.discount_label = discount.label if discount else None
    await order_svc.reprice(uow, ctx.venue, order)
    await order_svc.changed(uow, order, "order.member_added", ctx.actor)
    await uow.commit()
    return order_dict(order)


# ------------------------------------------------------------------ owner


@router.get("/admin/venues/{venue_id}/customers")
async def members(venue: AdminVenue, uow: Uow, q: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Customer).where(Customer.tenant_id == venue.tenant_id, Customer.forgotten_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.phone.like(like), Customer.name.ilike(like)))
    rows = (await uow.session.scalars(stmt.order_by(Customer.lifetime_points.desc()).limit(200))).all()
    return [loyalty.admin_dict(c, venue) for c in rows]


async def _member(uow: Uow, venue: AdminVenue, customer_id: str) -> Customer:
    c = await uow.session.get(Customer, customer_id)
    if c is None or c.tenant_id != venue.tenant_id:
        raise NotFound("Member")
    return c


@router.get("/admin/venues/{venue_id}/customers/{customer_id}/export")
async def export(customer_id: str, venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """Everything we keep about a member (PDPA access request)."""
    c = await _member(uow, venue, customer_id)
    orders = (await uow.session.scalars(select(Order).where(Order.customer_id == c.id))).all()
    return {
        "member": {**loyalty.admin_dict(c, venue), "consent_text": c.consent_text},
        "orders": [
            {"token": o.token, "date": o.business_date, "total": o.total, "points_earned": o.points_earned}
            for o in orders
        ],
    }


@router.post("/admin/venues/{venue_id}/customers/{customer_id}/forget")
async def forget(customer_id: str, venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """PDPA delete-on-request: the phone and name are removed; anonymous sales stay for the accounts."""
    c = await _member(uow, venue, customer_id)
    loyalty.forget(c)
    uow.session.add(c)
    await uow.commit()
    return loyalty.admin_dict(c, venue)
