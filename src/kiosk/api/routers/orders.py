from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from kiosk.api.deps import Ctx, DeviceCtx, Uow, require_staff
from kiosk.domain.orders import Status
from kiosk.errors import AppError, Forbidden, NotFound
from kiosk.infra.models import Invoice, Order, utcnow
from kiosk.services import idempotency, loyalty, printing, sms
from kiosk.services import orders as svc
from kiosk.services import payments as pay
from kiosk.services.menu import CartLine, local_now, price_cart
from kiosk.services.plans import require_module
from kiosk.services.serializers import order_dict, payment_dict
from kiosk.services.uow import UnitOfWork

router = APIRouter(prefix="/v1/orders", tags=["orders"])

ORDERING_DEVICES = {"cashier": "cashier", "kiosk": "kiosk", "table": "table", "waiter": "table"}
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]


class CartLineIn(BaseModel):
    menu_item_id: str
    quantity: int = Field(1, ge=1, le=99)
    modifier_ids: list[str] = []
    notes: str | None = Field(None, max_length=300)
    combo_choices: list[str] = Field(default=[], description="Combo: one menu item id per slot")
    hold: bool = Field(default=False, description="Staff: keep in the kitchen until fired (next course)")
    source: Literal["upsell"] | None = Field(
        default=None, description="'upsell' when added from a suggestion"
    )


class OrderIn(BaseModel):
    items: list[CartLineIn] = Field(min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=500)
    table_ref: str | None = Field(None, description="Waiter devices choose the table")
    customer_phone: str | None = Field(
        None, max_length=20, description="Loyalty member: points and tier price"
    )


def _cart(lines: list[CartLineIn]) -> list[CartLine]:
    return [
        CartLine(
            ln.menu_item_id, ln.quantity, ln.modifier_ids, ln.notes, ln.combo_choices, ln.hold, ln.source
        )
        for ln in lines
    ]


async def _idempotent(
    uow: UnitOfWork, scope: str, key: str | None, status: int, response: dict[str, Any]
) -> JSONResponse:
    """Store the response with the write, then commit. A concurrent duplicate loses the race
    on the unique key and gets the stored response instead."""
    idempotency.remember(uow.session, scope, key, status, response)
    try:
        await uow.commit()
    except IntegrityError:
        await uow.session.rollback()
        found = await idempotency.lookup(uow.session, scope, key)
        if found is None:
            raise
        return JSONResponse(found.response, status_code=found.status_code)
    return JSONResponse(response, status_code=status)


async def _replay(uow: UnitOfWork, scope: str, key: str | None) -> JSONResponse | None:
    found = await idempotency.lookup(uow.session, scope, key)
    if found:
        return JSONResponse(found.response, status_code=found.status_code)
    return None


@router.post("/quote")
async def quote(body: OrderIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Price a cart (subtotal, service charge, taxes) without creating an order."""
    discount = None
    if body.customer_phone:
        customer = await loyalty.find(uow, ctx.venue, body.customer_phone)
        if customer is not None and customer.consent_at and not customer.forgotten_at:
            discount = loyalty.discount_for(ctx.venue, customer)
    priced = await price_cart(uow.session, ctx.venue, _cart(body.items), utcnow(), discount)
    return priced.as_dict()


@router.post("", status_code=201)
async def create_order(body: OrderIn, ctx: Ctx, uow: Uow, idem: IdemKey = None) -> JSONResponse:
    scope = f"{ctx.venue.id}:orders.create:{ctx.device.id}"
    if cached := await _replay(uow, scope, idem):
        return cached
    channel = ORDERING_DEVICES.get(ctx.device.type)
    if channel is None:
        raise Forbidden("This device cannot place orders")
    if ctx.device.type in ("cashier", "waiter") and ctx.staff is None:
        raise Forbidden("Staff PIN login required")
    table_ref = ctx.device.table_ref if ctx.device.type == "table" else body.table_ref
    if ctx.device.type == "cashier" and table_ref:
        channel = "table"  # the POS ordering for a table: same check (tab) and rules as the table's own
    if ctx.device.type == "waiter" and not table_ref:
        raise AppError("table_ref_required", "Choose a table")
    member = None
    if body.customer_phone:
        customer = await loyalty.find(uow, ctx.venue, body.customer_phone)
        if customer is None or customer.forgotten_at or not customer.consent_at:
            raise NotFound("Member")
        member = (customer.id, loyalty.discount_for(ctx.venue, customer))
    order = await svc.create_order(
        uow, ctx.venue, ctx.actor, channel, _cart(body.items), table_ref, body.notes, member=member
    )
    return await _idempotent(uow, scope, idem, 201, order_dict(order))


@router.get("")
async def list_orders(
    ctx: Ctx,
    uow: Uow,
    status: Annotated[list[str] | None, Query()] = None,
    business_date: date | None = None,
    table_ref: str | None = None,
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    stmt = select(Order).where(Order.venue_id == ctx.venue.id)
    if status:
        stmt = stmt.where(Order.status.in_(status))
    if business_date:
        stmt = stmt.where(Order.business_date == business_date.isoformat())
    if table_ref:
        stmt = stmt.where(Order.table_ref == table_ref)
    rows = (await uow.session.scalars(stmt.order_by(Order.created_at.desc()).limit(limit))).all()
    return [order_dict(o) for o in rows]


@router.get("/lookup")
async def lookup(ctx: Ctx, uow: Uow, code: str) -> dict[str, Any]:
    """Find an order from a scanned barcode (order id) or a typed token / table number.

    Tokens are unique per business day, so a token search looks at today only.
    """
    code = code.strip()
    today = local_now(ctx.venue, utcnow()).date().isoformat()
    stmt = (
        select(Order)
        .where(
            Order.venue_id == ctx.venue.id,
            or_(
                Order.id == code,
                (Order.business_date == today) & (Order.token == code.upper()),
                (Order.business_date == today)
                & (Order.table_ref == code)
                & Order.status.notin_([Status.COMPLETED, Status.CANCELLED, Status.EXPIRED, Status.VOIDED]),
            ),
        )
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    order = await uow.session.scalar(stmt)
    if order is None:
        raise NotFound("Order")
    return order_dict(order)


@router.get("/{order_id}")
async def get_order(order_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id)
    inv = await uow.session.scalar(select(Invoice).where(Invoice.order_id == order.id))
    return {**order_dict(order), "invoice_number": inv.number if inv else None}


def _may_edit(ctx: DeviceCtx, order: Order) -> None:
    """Guests can only change orders from their own screen. Staff can change any."""
    if ctx.staff is None and order.device_id != ctx.device.id:
        raise Forbidden("Only the screen that placed this order, or staff, can change it")


@router.put("/{order_id}/items")
async def replace_items(order_id: str, body: OrderIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    _may_edit(ctx, order)
    await svc.replace_items(uow, ctx.venue, order, ctx.actor, _cart(body.items))
    await uow.commit()
    return order_dict(order)


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{order_id}/cancel")
async def cancel(order_id: str, body: Reason, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    _may_edit(ctx, order)
    await svc.cancel(uow, order, ctx.actor, body.reason)
    await uow.commit()
    return order_dict(order)


Manager = Annotated[DeviceCtx, Depends(require_staff("manager"))]
Cashier = Annotated[DeviceCtx, Depends(require_staff("cashier"))]
Server = Annotated[DeviceCtx, Depends(require_staff("cashier", "waiter"))]


@router.post("/{order_id}/served")
async def served(order_id: str, ctx: Server, uow: Uow) -> dict[str, Any]:
    """Waiter took the ready food to the table (waiter-serve venues)."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.mark_served(uow, order, ctx.actor)
    await uow.commit()
    return order_dict(order)


class PriorityIn(BaseModel):
    priority: Literal["normal", "vip", "rush"]


@router.post("/{order_id}/priority")
async def set_priority(order_id: str, body: PriorityIn, ctx: Server, uow: Uow) -> dict[str, Any]:
    """Staff mark an order rush or VIP; the kitchen queue puts it first."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.set_priority(uow, order, ctx.actor, body.priority)
    await uow.commit()
    return order_dict(order)


class FireIn(BaseModel):
    item_ids: list[str] | None = Field(default=None, description="Items to fire; empty = all held items")


@router.post("/{order_id}/fire")
async def fire(order_id: str, ctx: Ctx, uow: Uow, body: FireIn | None = None) -> dict[str, Any]:
    """Send held items to the kitchen (next course). Staff, or a kitchen screen."""
    if ctx.staff is None and ctx.device.type != "kds":
        raise Forbidden("Staff or a kitchen screen must fire held items")
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.fire(uow, order, ctx.actor, body.item_ids if body else None)
    await uow.commit()
    return order_dict(order)


@router.post("/{order_id}/void")
async def void(order_id: str, body: Reason, ctx: Manager, uow: Uow) -> dict[str, Any]:
    """Manager only. Stops a kitchen order and refunds any payment."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.void(uow, order, ctx.actor, body.reason)
    if order.payment_status == "paid":
        await pay.refund_all(uow, ctx.venue, order, ctx.actor, body.reason)
    await uow.commit()
    return order_dict(order)


@router.post("/{order_id}/refund")
async def refund(order_id: str, body: Reason, ctx: Manager, uow: Uow) -> dict[str, Any]:
    """Manager only. Refund a paid order (e.g. a complaint after handover)."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await pay.refund_all(uow, ctx.venue, order, ctx.actor, body.reason)
    await uow.commit()
    return order_dict(order)


@router.post("/{order_id}/complete")
async def complete(order_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Handed over to the guest. Done by staff, or by an expo KDS / cashier device."""
    if ctx.staff is None and ctx.device.type not in ("kds", "cashier"):
        raise Forbidden("Staff or a kitchen/cashier device must hand over orders")
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.complete(uow, order, ctx.actor)
    await uow.commit()
    return order_dict(order)


# ------------------------------------------------------------------ payments


class CashIn(BaseModel):
    tendered: int = Field(gt=0, description="LKR cents handed over")
    amount: int | None = Field(default=None, gt=0, description="Split bill: this share (LKR cents)")


class CardIn(BaseModel):
    approval_code: str = Field(min_length=1, max_length=80)
    amount: int | None = Field(default=None, gt=0, description="Split bill: this share (LKR cents)")


class PartIn(BaseModel):
    amount: int | None = Field(default=None, gt=0, description="Split bill: this share (LKR cents)")


@router.post("/{order_id}/payment-hold")
async def hold_payment(order_id: str, ctx: Server, uow: Uow) -> dict[str, Any]:
    """Start taking a payment. The bill is held for you for two minutes, so nobody takes it twice;
    everyone else sees who is taking it. Call again to keep it while you wait for the guest."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    pay.hold_payment(order, ctx.actor, ctx.staff.name if ctx.staff else "Staff")
    await svc.changed(uow, order, "order.payment_hold", ctx.actor)
    await uow.commit()
    return order_dict(order)


@router.delete("/{order_id}/payment-hold")
async def release_payment(order_id: str, ctx: Server, uow: Uow) -> dict[str, Any]:
    """Not taking it after all (closed the payment window). A manager can free someone else's hold."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    manager = bool(ctx.staff and ctx.staff.role in ("manager", "owner"))
    pay.release_payment(order, ctx.actor, force=manager)
    await svc.changed(uow, order, "order.payment_hold", ctx.actor)
    await uow.commit()
    return order_dict(order)


@router.post("/{order_id}/payments/cash", status_code=201)
async def pay_cash(order_id: str, body: CashIn, ctx: Server, uow: Uow, idem: IdemKey = None) -> JSONResponse:
    """Cash at the POS, or at the table by a waiter (into the waiter's own cash bag)."""
    scope = f"{ctx.venue.id}:pay.cash:{order_id}"
    if cached := await _replay(uow, scope, idem):
        return cached
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    payment = await pay.pay_cash(uow, ctx.venue, order, ctx.actor, body.tendered, body.amount)
    return await _idempotent(
        uow,
        scope,
        idem,
        201,
        {"payment": payment_dict(payment), "order": order_dict(order), "printed_at": uow.printed},
    )


@router.post("/{order_id}/payments/card", status_code=201)
async def pay_card(order_id: str, body: CardIn, ctx: Server, uow: Uow, idem: IdemKey = None) -> JSONResponse:
    """Card on the bank's own machine (at the counter or brought to the table): its approval code."""
    scope = f"{ctx.venue.id}:pay.card:{order_id}"
    if cached := await _replay(uow, scope, idem):
        return cached
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    payment = await pay.pay_card(uow, ctx.venue, order, ctx.actor, body.approval_code, body.amount)
    return await _idempotent(
        uow,
        scope,
        idem,
        201,
        {"payment": payment_dict(payment), "order": order_dict(order), "printed_at": uow.printed},
    )


@router.post("/{order_id}/payments/lankaqr", status_code=201)
async def pay_lankaqr(order_id: str, ctx: Ctx, uow: Uow, body: PartIn | None = None) -> dict[str, Any]:
    """Start (or re-show) a dynamic LankaQR code. Payment completes via the gateway callback."""
    require_module(ctx.venue, "R-PAY")
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    _may_edit(ctx, order)
    payment = await pay.start_lankaqr(uow, ctx.venue, order, ctx.actor, body.amount if body else None)
    await uow.commit()
    return {"payment": payment_dict(payment), "order": order_dict(order), "printed_at": uow.printed}


@router.post("/{order_id}/payments/card-terminal", status_code=201)
async def pay_card_terminal(
    order_id: str, ctx: Ctx, uow: Uow, idem: IdemKey = None, body: PartIn | None = None
) -> JSONResponse:
    """Charge the order on this screen's card terminal (built-in reader, or tap on a staff tablet).

    Returns a pending payment. It completes when the processor's signed callback arrives.
    """
    scope = f"{ctx.venue.id}:pay.card_terminal:{order_id}"
    if cached := await _replay(uow, scope, idem):
        return cached
    require_module(ctx.venue, "R-PAY")
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    _may_edit(ctx, order)
    payment = await pay.start_card(
        uow, ctx.venue, order, ctx.actor, ctx.device, body.amount if body else None
    )
    return await _idempotent(
        uow,
        scope,
        idem,
        201,
        {"payment": payment_dict(payment), "order": order_dict(order), "printed_at": uow.printed},
    )


@router.post("/{order_id}/payments/{payment_id}/cancel")
async def cancel_payment(order_id: str, payment_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Stop waiting for a card tap or QR scan (the guest pressed Cancel)."""
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    _may_edit(ctx, order)
    payment = await pay.cancel_payment(uow, order, ctx.actor, payment_id)
    await uow.commit()
    return {"payment": payment_dict(payment), "order": order_dict(order), "printed_at": uow.printed}


# ------------------------------------------------------------------ printing

PrintKind = Literal["receipt", "token", "kitchen"]


@router.post("/{order_id}/print/{kind}", status_code=202)
async def reprint(order_id: str, kind: PrintKind, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Staff can print anything. A guest screen can print its own order's token slip
    (e.g. a kiosk "Pay at cashier" slip)."""
    order = await svc.get_order(uow, ctx.venue.id, order_id)
    if ctx.staff is None and not (kind == "token" and order.device_id == ctx.device.id):
        raise Forbidden("Staff PIN login required")
    if kind == "receipt":
        inv = await uow.session.scalar(select(Invoice).where(Invoice.order_id == order.id))
        data, role = printing.render_receipt(ctx.venue, order, inv, drawer=False), "receipt"
    elif kind == "token":
        data, role = printing.render_token(ctx.venue, order), "token"
    else:
        data, role = printing.render_kitchen_ticket(order), "kitchen"
    uow.audit(ctx.actor, "print.reprint", order.id, kind=kind)
    await printing.enqueue(uow, ctx.venue, role, data, f"{kind}-{order.token}", order, source=ctx.device.id)
    await uow.commit()
    return {"queued": True}


# ------------------------------------------------------------------ texts to the guest


class NotifyIn(BaseModel):
    phone: str = Field(min_length=7, max_length=20)


@router.post("/{order_id}/notify")
async def notify_me(order_id: str, body: NotifyIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """The guest leaves a mobile number: a text when the order is ready (and a receipt link).
    Used for this order only."""
    order = await svc.get_order(uow, ctx.venue.id, order_id)
    if ctx.staff is None and order.device_id != ctx.device.id:
        raise Forbidden("Only the screen that took the order, or staff")
    order.notify_phone = loyalty.normalize_phone(body.phone)
    await svc.changed(uow, order, "order.notify_set", ctx.actor)
    queued = []
    if order.status == Status.READY:
        queued.append(await sms.queue(uow, ctx.venue, order, "ready"))
    if order.payment_status == "paid":
        queued.append(await sms.queue(uow, ctx.venue, order, "receipt"))
    uow.audit(ctx.actor, "order.notify_set", order.id)
    await uow.commit()
    return {**order_dict(order), "texts_now": len([q for q in queued if q])}
