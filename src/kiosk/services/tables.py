"""Opening and closing tables (table_access = "staff_opens").

Real use: an empty table's screen must not take orders (children, passers-by, a table nobody sits
at). Staff open the table on the POS when guests sit down; guests then order and pay as usual.
When they leave, staff close the table: its screen goes back to the welcome screen and nothing of
the last guests stays. A tab that is paid closes its table by itself.

With table_access = "open" every table is always open (no staff step).
"""

from typing import Any

from sqlalchemy import select

from kiosk.domain.orders import PaymentStatus, Status
from kiosk.errors import AppError, Conflict
from kiosk.infra.models import Order, ServiceRequest, TableState, Venue, utcnow
from kiosk.services.uow import Actor, UnitOfWork


def staff_opens(venue: Venue) -> bool:
    return bool(venue.setting("table_access") == "staff_opens")


async def state(uow: UnitOfWork, venue_id: str, table_ref: str) -> TableState | None:
    return await uow.session.get(TableState, (venue_id, table_ref))


async def is_open(uow: UnitOfWork, venue: Venue, table_ref: str) -> bool:
    if not staff_opens(venue):
        return True
    row = await state(uow, venue.id, table_ref)
    return bool(row and row.is_open)


async def ensure_can_order(uow: UnitOfWork, venue: Venue, table_ref: str, actor: Actor) -> None:
    """Guests can order only at an open table. Staff ordering for a table opens it."""
    if not staff_opens(venue):
        return
    if actor.staff_id is not None:
        await set_open(uow, venue, table_ref, True, actor)
        return
    if not await is_open(uow, venue, table_ref):
        raise AppError("table_closed", "This table is not open yet. Please call our staff", 409)


def _emit(uow: UnitOfWork, venue_id: str, table_ref: str, is_open_: bool) -> None:
    uow.emit(
        venue_id, "table.state", {"table_ref": table_ref, "open": is_open_}, ["orders", "service", "status"]
    )


async def set_open(uow: UnitOfWork, venue: Venue, table_ref: str, open_: bool, actor: Actor) -> TableState:
    row = await state(uow, venue.id, table_ref)
    if row is None:
        row = TableState(venue_id=venue.id, table_ref=table_ref, is_open=False)
        uow.session.add(row)
    if row.is_open == open_:
        return row
    row.is_open = open_
    if open_:
        row.opened_at, row.opened_by, row.closed_at = utcnow(), actor.staff_id, None
        # The guests called staff to be seated: opening the table answers that call.
        calls = (
            await uow.session.scalars(
                select(ServiceRequest).where(
                    ServiceRequest.venue_id == venue.id,
                    ServiceRequest.table_ref == table_ref,
                    ServiceRequest.kind == "call_waiter",
                    ServiceRequest.status != "done",
                )
            )
        ).all()
        for c in calls:
            c.status = "done"
    else:
        row.closed_at = utcnow()
    uow.audit(actor, "table.open" if open_ else "table.close", table_ref)
    _emit(uow, venue.id, table_ref, open_)
    return row


async def _row(uow: UnitOfWork, venue: Venue, table_ref: str) -> TableState:
    row = await state(uow, venue.id, table_ref)
    if row is None:
        row = TableState(venue_id=venue.id, table_ref=table_ref, is_open=False, needs_cleaning=False)
        uow.session.add(row)
    return row


def _emit_visit(uow: UnitOfWork, venue_id: str, row: TableState) -> None:
    uow.emit(
        venue_id,
        "table.visit",
        {
            "table_ref": row.table_ref,
            "occupied": row.occupied_since is not None,
            "needs_cleaning": row.needs_cleaning,
        },
        ["orders", "service"],
    )


async def start_visit(uow: UnitOfWork, venue: Venue, table_ref: str) -> None:
    """Guests ordered at this table: it is occupied (and evidently ready for them)."""
    row = await _row(uow, venue, table_ref)
    if row.occupied_since is None or row.needs_cleaning:
        row.occupied_since = row.occupied_since or utcnow()
        row.needs_cleaning = False
        _emit_visit(uow, venue.id, row)


async def end_visit(uow: UnitOfWork, venue: Venue, table_ref: str) -> None:
    """Guests paid / left: the visit is over (its calls too); the table needs cleaning next."""
    row = await _row(uow, venue, table_ref)
    row.occupied_since = None
    row.needs_cleaning = True
    calls = (
        await uow.session.scalars(
            select(ServiceRequest).where(
                ServiceRequest.venue_id == venue.id,
                ServiceRequest.table_ref == table_ref,
                ServiceRequest.status != "done",
            )
        )
    ).all()
    for c in calls:
        c.status, c.done_at = "done", utcnow()
        uow.emit(
            venue.id,
            "service.done",
            {
                "request": {
                    "id": c.id,
                    "kind": c.kind,
                    "table_ref": table_ref,
                    "device_id": c.device_id,
                    "status": "done",
                }
            },
            ["orders", "service"],
        )
    _emit_visit(uow, venue.id, row)


async def cleaned(uow: UnitOfWork, venue: Venue, table_ref: str, actor: Actor) -> TableState:
    """A waiter cleaned and reset the table: it is free for the next guests."""
    row = await _row(uow, venue, table_ref)
    row.needs_cleaning = False
    row.cleaned_at, row.cleaned_by = utcnow(), actor.staff_id
    uow.audit(actor, "table.cleaned", table_ref)
    _emit_visit(uow, venue.id, row)
    return row


async def unpaid(uow: UnitOfWork, venue_id: str, table_ref: str) -> list[Order]:
    rows = await uow.session.scalars(
        select(Order).where(
            Order.venue_id == venue_id,
            Order.table_ref == table_ref,
            Order.status.in_([Status.PLACED, Status.IN_KITCHEN, Status.READY]),
            Order.payment_status != PaymentStatus.PAID,
        )
    )
    return list(rows.all())


async def close(uow: UnitOfWork, venue: Venue, table_ref: str, actor: Actor) -> dict[str, Any]:
    """Guests have left. Refused while the table still owes money (pay or void first).
    Paid orders still open are finished, and the table's calls are cleared."""
    owing = await unpaid(uow, venue.id, table_ref)
    if owing:
        left = sum(o.total - o.paid_total for o in owing)
        raise Conflict(
            "table_unpaid",
            f"Table {table_ref} still owes Rs {left / 100:,.2f} ({', '.join(o.token for o in owing)}). "
            "Take payment first",
        )
    from kiosk.services import orders as order_svc  # avoid an import cycle

    done = (
        await uow.session.scalars(
            select(Order).where(
                Order.venue_id == venue.id,
                Order.table_ref == table_ref,
                Order.status.in_([Status.IN_KITCHEN, Status.READY]),
                Order.payment_status == PaymentStatus.PAID,
            )
        )
    ).all()
    finished = []
    for o in done:
        if o.status == Status.READY:  # food is on the table: the visit is over
            await order_svc.complete(uow, o, actor)
            finished.append(o.token)
    calls = (
        await uow.session.scalars(
            select(ServiceRequest).where(
                ServiceRequest.venue_id == venue.id,
                ServiceRequest.table_ref == table_ref,
                ServiceRequest.status != "done",
            )
        )
    ).all()
    for c in calls:
        c.status = "done"
    await set_open(uow, venue, table_ref, False, actor)
    await end_visit(uow, venue, table_ref)  # next: clean the table
    # Tell this table's screen to start fresh for the next guests.
    uow.emit(venue.id, "table.cleared", {"table_ref": table_ref}, ["orders", "service", "status"])
    return {"table_ref": table_ref, "open": False, "finished": finished, "calls_cleared": len(calls)}


async def bill_settled(uow: UnitOfWork, venue: Venue, table_ref: str) -> None:
    """The table owes nothing now: its "wants the bill" calls are answered (gone from every screen)."""
    if await unpaid(uow, venue.id, table_ref):
        return
    calls = (
        await uow.session.scalars(
            select(ServiceRequest).where(
                ServiceRequest.venue_id == venue.id,
                ServiceRequest.table_ref == table_ref,
                ServiceRequest.kind == "request_bill",
                ServiceRequest.status != "done",
            )
        )
    ).all()
    for c in calls:
        c.status, c.done_at = "done", utcnow()
        data = {
            "id": c.id,
            "kind": c.kind,
            "where": c.where,
            "table_ref": table_ref,
            "device_id": c.device_id,
        }
        uow.emit(venue.id, "service.done", {"request": {**data, "status": "done"}}, ["orders", "service"])


async def bill(uow: UnitOfWork, venue: Venue, table_ref: str) -> dict[str, Any]:
    """Everything the table still has to pay, as one bill (all its unpaid orders)."""
    owing = await unpaid(uow, venue.id, table_ref)
    if not owing:
        raise AppError("nothing_to_pay", f"Table {table_ref} has nothing to pay", 409)
    owing.sort(key=lambda o: o.created_at)
    lines = [
        {
            "name": i.name,
            "quantity": i.quantity,
            "line_total": i.line_total,
            "part": i.parent_position is not None,
        }
        for o in owing
        for i in o.items
        if i.kds_status != "voided"
    ]
    return {
        "table_ref": table_ref,
        "orders": [
            {"id": o.id, "token": o.token, "due": o.total - o.paid_total, "is_tab": o.is_tab} for o in owing
        ],
        "lines": lines,
        "subtotal": sum(o.subtotal for o in owing),
        "discount_total": sum(o.discount_total for o in owing),
        "tax_total": sum(o.tax_total for o in owing),
        "total": sum(o.total for o in owing),
        "paid_total": sum(o.paid_total for o in owing),
        "due": sum(o.total - o.paid_total for o in owing),
    }


async def print_bill(uow: UnitOfWork, venue: Venue, table_ref: str, actor: Actor) -> dict[str, Any]:
    from kiosk.services import printing  # printing imports the ordering services

    data = await bill(uow, venue, table_ref)
    owing = await unpaid(uow, venue.id, table_ref)
    slip = printing.render_bill(venue, table_ref, sorted(owing, key=lambda o: o.created_at))
    jobs = await printing.enqueue(uow, venue, "receipt", slip, f"bill-{table_ref}", source=actor.device_id)
    uow.audit(actor, "table.bill_printed", table_ref, due=data["due"])
    # Where it came out, so the waiter knows where to pick it up ("at the counter").
    return {**data, "printed": True, "print_jobs": len(jobs), "printed_at": uow.printed}
