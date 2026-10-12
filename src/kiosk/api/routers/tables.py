"""Table map for waiters and cashiers: every table's live state at a glance."""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from kiosk.api.deps import Ctx, Uow
from kiosk.domain.orders import Status
from kiosk.errors import Forbidden
from kiosk.infra.models import Device, Feedback, Order, ServiceRequest, Staff, TableState, utcnow
from kiosk.services import tables
from kiosk.services.feedback import feedback_dict

router = APIRouter(prefix="/v1/tables", tags=["tables"])

# A table's visit, most urgent first (the state shown is the first that applies):
#   calling · wants the bill · food ready (take it to the table) · waiting payment · cooking ·
#   eating (guests are there) · needs cleaning (guests left) · free · closed (staff open tables).
STATES = ("calling", "bill", "ready", "waiting_payment", "cooking", "eating", "cleaning", "free", "closed")


@router.get("")
async def table_map(ctx: Ctx, uow: Uow) -> list[dict[str, Any]]:
    if ctx.device.type not in ("cashier", "waiter") and ctx.staff is None:
        raise Forbidden("The table map is for staff screens")
    venue = ctx.venue.id
    staff_opens = tables.staff_opens(ctx.venue)
    names = dict(
        (await uow.session.execute(select(Staff.id, Staff.name).where(Staff.venue_id == venue))).all()
    )
    rows = {
        s.table_ref: s
        for s in (await uow.session.scalars(select(TableState).where(TableState.venue_id == venue))).all()
    }
    opened = {ref: s.is_open for ref, s in rows.items()}
    recent = (
        await uow.session.scalars(
            select(Feedback)
            .where(Feedback.venue_id == venue, Feedback.created_at >= utcnow() - timedelta(hours=3))
            .order_by(Feedback.created_at.desc())
        )
    ).all()
    devices = (
        await uow.session.scalars(
            select(Device).where(Device.venue_id == venue, Device.type == "table", Device.is_active)
        )
    ).all()
    orders = (
        await uow.session.scalars(
            select(Order).where(
                Order.venue_id == venue,
                Order.table_ref.is_not(None),
                Order.status.in_([Status.PLACED, Status.IN_KITCHEN, Status.READY]),
            )
        )
    ).all()
    calls = (
        await uow.session.scalars(
            select(ServiceRequest).where(ServiceRequest.venue_id == venue, ServiceRequest.status != "done")
        )
    ).all()
    refs = sorted(
        {d.table_ref for d in devices if d.table_ref} | {o.table_ref for o in orders if o.table_ref},
        key=lambda r: (len(r), r),
    )
    out = []
    for ref in refs:
        mine = [o for o in orders if o.table_ref == ref]
        reqs = [r for r in calls if r.table_ref == ref]
        flags = {
            "calling": any(r.kind == "call_waiter" for r in reqs),
            "bill": any(r.kind == "request_bill" for r in reqs),
            "ready": any(o.status == Status.READY and not o.served_at for o in mine),
            "waiting_payment": any(o.status == Status.PLACED and o.payment_status != "paid" for o in mine),
            "cooking": any(o.status == Status.IN_KITCHEN for o in mine),
            "eating": bool(mine) or bool(rows.get(ref) and rows[ref].occupied_since),
            "cleaning": bool(rows.get(ref) and rows[ref].needs_cleaning),
        }
        is_open = (not staff_opens) or opened.get(ref, False)
        state = next((s for s in STATES if flags.get(s)), "free" if is_open else "closed")
        out.append(
            {
                "table_ref": ref,
                "state": state,
                "open": is_open,
                "screens": [d.name for d in devices if d.table_ref == ref],
                "requests": [
                    {
                        "id": r.id,
                        "kind": r.kind,
                        "status": r.status,
                        "pay_with": r.pay_with,
                        "coming": names.get(r.acknowledged_by or "") if r.acknowledged_by else None,
                    }
                    for r in reqs
                ],
                "orders": [
                    {
                        "id": o.id,
                        "token": o.token,
                        "status": o.status,
                        "payment_status": o.payment_status,
                        "total": o.total,
                        "paid_total": o.paid_total,
                        "is_tab": o.is_tab,
                        "served": bool(o.served_at),
                    }
                    for o in sorted(mine, key=lambda o: o.created_at)
                ],
                "open_total": sum(o.total - o.paid_total for o in mine),
                # Food to take to the table now (ready in the kitchen, not served yet).
                "to_serve": [
                    {"id": o.id, "token": o.token}
                    for o in mine
                    if o.status == Status.READY and not o.served_at
                ],
                "occupied_since": since.isoformat()
                if (since := getattr(rows.get(ref), "occupied_since", None))
                else None,
                "needs_cleaning": bool(rows.get(ref) and rows[ref].needs_cleaning),
                "feedback": next(
                    (feedback_dict(f) for f in recent if f.table_ref == ref),
                    None,
                ),
            }
        )
    return out


def _staff(ctx: Any) -> None:
    if ctx.staff is None:
        raise Forbidden("Staff PIN login required")


@router.post("/{table_ref}/open")
async def open_table(table_ref: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Guests sat down: their table screen can take orders now."""
    _staff(ctx)
    await tables.set_open(uow, ctx.venue, table_ref, True, ctx.actor)
    await uow.commit()
    return {"table_ref": table_ref, "open": True}


@router.post("/{table_ref}/close")
async def close_table(table_ref: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Guests left (everything paid): the table goes back to its welcome screen, locked."""
    _staff(ctx)
    result = await tables.close(uow, ctx.venue, table_ref, ctx.actor)
    await uow.commit()
    return result


@router.post("/{table_ref}/cleaned")
async def table_cleaned(table_ref: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """The table is cleaned and reset for the next guests."""
    _staff(ctx)
    row = await tables.cleaned(uow, ctx.venue, table_ref, ctx.actor)
    await uow.commit()
    return {"table_ref": table_ref, "needs_cleaning": row.needs_cleaning}


@router.get("/{table_ref}/bill")
async def table_bill(table_ref: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """What the table still has to pay (all its unpaid orders as one bill)."""
    _staff(ctx)
    return await tables.bill(uow, ctx.venue, table_ref)


@router.post("/{table_ref}/bill")
async def print_table_bill(table_ref: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """Print the bill to bring to the table (on this screen's printer or the receipt printer)."""
    _staff(ctx)
    result = await tables.print_bill(uow, ctx.venue, table_ref, ctx.actor)
    await uow.commit()
    return result
