from typing import Any

from sqlalchemy import select

from kiosk.errors import AppError, Conflict, NotFound
from kiosk.infra.models import CashShift, Payment, utcnow
from kiosk.services.payments import open_shift_for
from kiosk.services.uow import Actor, UnitOfWork


def shift_dict(s: CashShift) -> dict[str, Any]:
    return {
        "id": s.id,
        "device_id": s.device_id,
        "opened_by": s.opened_by,
        "opening_float": s.opening_float,
        "opened_at": s.opened_at.isoformat(),
        "closed_by": s.closed_by,
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        "counted_cash": s.counted_cash,
        "expected_cash": s.expected_cash,
        "variance": s.variance,
        "report": s.report,
    }


async def open_shift(uow: UnitOfWork, actor: Actor, opening_float: int) -> CashShift:
    assert actor.device_id and actor.staff_id
    if await open_shift_for(uow, actor.venue_id, actor.device_id):
        raise Conflict("shift_open", "A shift is already open on this device")
    if opening_float < 0:
        raise AppError("bad_amount", "Opening float cannot be negative")
    shift = CashShift(
        venue_id=actor.venue_id,
        device_id=actor.device_id,
        opened_by=actor.staff_id,
        opening_float=opening_float,
    )
    uow.session.add(shift)
    uow.audit(actor, "shift.open", None, opening_float=opening_float)
    await uow.session.flush()
    # The other side knows the drawer is open (backup mode can take cash on the same shift).
    uow.outbox(actor.venue_id, "shift", shift_dict(shift))
    return shift


async def shift_report(uow: UnitOfWork, shift: CashShift) -> dict[str, Any]:
    payments = (
        await uow.session.scalars(
            select(Payment).where(Payment.shift_id == shift.id, Payment.status == "succeeded")
        )
    ).all()
    by_method: dict[str, dict[str, int]] = {}
    for p in payments:
        m = by_method.setdefault(p.method, {"charges": 0, "refunds": 0, "count": 0})
        m["refunds" if p.kind == "refund" else "charges"] += p.amount
        m["count"] += 1
    cash = by_method.get("cash", {"charges": 0, "refunds": 0})
    expected = shift.opening_float + cash["charges"] - cash["refunds"]
    return {"by_method": by_method, "expected_cash": expected}


async def close_shift(uow: UnitOfWork, actor: Actor, shift_id: str, counted_cash: int) -> CashShift:
    shift = await uow.session.get(CashShift, shift_id)
    if shift is None or shift.venue_id != actor.venue_id:
        raise NotFound("Shift")
    if shift.closed_at is not None:
        raise Conflict("shift_closed", "This shift is already closed")
    report = await shift_report(uow, shift)
    shift.closed_at = utcnow()
    shift.closed_by = actor.staff_id
    shift.counted_cash = counted_cash
    shift.expected_cash = report["expected_cash"]
    shift.variance = counted_cash - report["expected_cash"]
    shift.report = report
    uow.audit(actor, "shift.close", shift.id, variance=shift.variance)
    uow.outbox(actor.venue_id, "shift", shift_dict(shift))
    await uow.session.flush()
    return shift
