from collections import Counter
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from kiosk.api.deps import Ctx, DeviceCtx, Uow, require_device
from kiosk.domain.orders import PRIORITY_RANK, ItemStatus, Status, congestion
from kiosk.infra.models import Order, Venue, utcnow
from kiosk.services import orders as svc
from kiosk.services.menu import COMBO_STATION
from kiosk.services.serializers import item_dict, order_dict

router = APIRouter(prefix="/v1", tags=["kitchen"])

KdsDevice = Annotated[DeviceCtx, Depends(require_device("kds"))]


def _station(ctx: DeviceCtx, station: str | None) -> str | None:
    """A station screen defaults to its own station; an expo screen (no station) sees all."""
    return station if station is not None else ctx.device.station


def _ticket(order: Order, station: str | None, warn: int, late: int) -> dict[str, Any] | None:
    items = [
        i
        for i in order.items
        if i.kds_status != ItemStatus.VOIDED
        and i.station != COMBO_STATION
        and (station is None or i.station == station)
    ]
    if not items:
        return None
    since = order.released_at or order.created_at
    age = int((utcnow() - since).total_seconds())
    colour = "red" if age >= late * 60 else "yellow" if age >= warn * 60 else "green"
    return {
        "order_id": order.id,
        "version": order.version,
        "priority": order.priority,
        "promised_at": order.promised_at.isoformat() if order.promised_at else None,
        "token": order.token,
        "channel": order.channel,
        "table_ref": order.table_ref,
        "status": order.status,
        "payment_status": order.payment_status,
        "notes": order.notes,
        "released_at": since.isoformat(),
        "age_seconds": age,
        "colour": colour,
        "items": [item_dict(i) for i in items],
        "station_done": all(i.kds_status == ItemStatus.DONE for i in items),
        "held": sum(1 for i in items if i.kds_status == ItemStatus.HELD),
    }


async def _kitchen_orders(uow: Uow, venue_id: str) -> list[Order]:
    rows = (
        await uow.session.scalars(
            select(Order)
            .where(Order.venue_id == venue_id, Order.status.in_([Status.IN_KITCHEN, Status.READY]))
            .order_by(Order.released_at)
        )
    ).all()
    # Rush first, then VIP, then by promised time (oldest first).
    return sorted(
        rows, key=lambda o: (PRIORITY_RANK.get(o.priority, 2), o.promised_at or o.released_at or o.created_at)
    )


@router.get("/kds/tickets")
async def tickets(ctx: KdsDevice, uow: Uow, station: str | None = None) -> dict[str, Any]:
    """Open tickets, oldest first. Timer colours use the venue's warn/late minutes."""
    st = _station(ctx, station)
    warn, late = int(ctx.venue.setting("kds_warn_minutes")), int(ctx.venue.setting("kds_late_minutes"))
    out = []
    for order in await _kitchen_orders(uow, ctx.venue.id):
        if order.status == Status.READY and order.served_at:
            continue  # a waiter already took it to the table (tab waiting for payment)
        t = _ticket(order, st, warn, late)
        if t and not (st is not None and t["station_done"] and order.status == Status.IN_KITCHEN):
            out.append(t)
    return {"station": st, "tickets": out}


@router.get("/kds/summary")
async def summary(ctx: KdsDevice, uow: Uow, station: str | None = None) -> dict[str, Any]:
    """All-day counts: how many of each item are still to cook."""
    st = _station(ctx, station)
    counts: Counter[str] = Counter()
    for order in await _kitchen_orders(uow, ctx.venue.id):
        for i in order.items:
            if i.kds_status in (ItemStatus.QUEUED, ItemStatus.IN_PROGRESS) and (
                st is None or i.station == st
            ):
                counts[i.name.get("en", i.menu_item_id)] += i.quantity
    return {"station": st, "to_cook": [{"name": n, "quantity": q} for n, q in counts.most_common()]}


@router.post("/kds/orders/{order_id}/items/{item_id}/start")
async def start_item(order_id: str, item_id: str, ctx: KdsDevice, uow: Uow) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.item_start(uow, order, item_id, ctx.actor)
    await uow.commit()
    return order_dict(order)


@router.post("/kds/orders/{order_id}/items/{item_id}/done")
async def done_item(order_id: str, item_id: str, ctx: KdsDevice, uow: Uow) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.item_done(uow, order, item_id, ctx.actor)
    await uow.commit()
    return order_dict(order)


class StationIn(BaseModel):
    station: str | None = None


@router.post("/kds/orders/{order_id}/bump")
async def bump(order_id: str, ctx: KdsDevice, uow: Uow, body: StationIn | None = None) -> dict[str, Any]:
    st = _station(ctx, body.station if body else None)
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.bump(uow, order, st, ctx.actor)
    await uow.commit()
    return order_dict(order)


class RemakeIn(BaseModel):
    reason: str


@router.post("/kds/orders/{order_id}/items/{item_id}/remake")
async def remake_item(
    order_id: str, item_id: str, body: RemakeIn, ctx: KdsDevice, uow: Uow
) -> dict[str, Any]:
    order = await svc.get_order(uow, ctx.venue.id, order_id, lock=True)
    await svc.remake(uow, order, item_id, ctx.actor, body.reason)
    await uow.commit()
    return order_dict(order)


async def kitchen_load(uow: Uow, venue: Venue) -> dict[str, Any]:
    """Congestion score for the kitchen, from open tickets and recent prep times."""
    orders = await _kitchen_orders(uow, venue.id)
    open_tickets = sum(1 for o in orders if o.status == Status.IN_KITCHEN)
    since = utcnow() - timedelta(hours=2)
    recent = (
        await uow.session.execute(
            select(Order.released_at, Order.ready_at).where(
                Order.venue_id == venue.id, Order.ready_at.is_not(None), Order.ready_at >= since
            )
        )
    ).all()
    preps = [(r - s).total_seconds() for s, r in recent if s and r]
    avg = sum(preps) / len(preps) if preps else int(venue.setting("default_prep_minutes")) * 60
    cooks = int(venue.setting("kitchen_cooks"))
    load = congestion(
        open_tickets,
        avg,
        cooks,
        int(venue.setting("kds_warn_minutes")),
        int(venue.setting("kds_late_minutes")),
    )
    return {"open_tickets": open_tickets, "avg_prep_seconds": round(avg), "cooks": cooks, **load}


@router.get("/kds/load")
async def load(ctx: Ctx, uow: Uow) -> dict[str, Any]:
    return await kitchen_load(uow, ctx.venue)


@router.post("/kds/recall")
async def recall(ctx: KdsDevice, uow: Uow, body: StationIn | None = None) -> dict[str, Any]:
    st = _station(ctx, body.station if body else None)
    order = await svc.recall(uow, ctx.venue.id, st, ctx.actor)
    await uow.commit()
    return order_dict(order)


@router.get("/status-board", tags=["status board"])
async def status_board(ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Tokens that are preparing, and tokens ready for pickup (recent ones only)."""
    minutes = int(ctx.venue.setting("ready_display_minutes"))
    cutoff = utcnow() - timedelta(minutes=minutes)
    rows = await _kitchen_orders(uow, ctx.venue.id)
    preparing = [o for o in rows if o.status == Status.IN_KITCHEN]
    ready = [
        o
        for o in rows
        if o.status == Status.READY and o.ready_at and o.ready_at >= cutoff and not o.served_at
    ]
    ready.sort(key=lambda o: o.ready_at or o.created_at, reverse=True)

    def row(o: Order) -> dict[str, Any]:
        return {
            "token": o.token,
            "table_ref": o.table_ref,
            "channel": o.channel,
            "unpaid": o.payment_status != "paid",
        }

    return {"preparing": [row(o) for o in preparing], "ready": [row(o) for o in ready]}
