"""The payment ledger: every payment and refund, traceable the standard way.

Each line answers: when, which order (number, table, channel), how (method), how much (amount, cash
received and change), who took it (staff), on which screen, the outside reference (bank approval
code, QR or card terminal reference, the restaurant POS's receipt number), the invoice number, and
the cash shift or waiter's cash bag it belongs to. Refunds point at the payment they reverse.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from kiosk.infra.models import Device, Invoice, Order, Payment, Staff, Venue
from kiosk.services.uow import UnitOfWork


def _day_bounds(venue: Venue, day: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(venue.timezone))
    return start, start + timedelta(days=1)


async def ledger(
    uow: UnitOfWork,
    venue: Venue,
    day: str | None = None,
    method: str | None = None,
    staff_id: str | None = None,
    device_id: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    q = (
        select(Payment, Order)
        .join(Order, Order.id == Payment.order_id)
        .where(Payment.venue_id == venue.id, Payment.status.in_(["succeeded", "pending", "failed"]))
    )
    if day:
        start, end = _day_bounds(venue, day)
        q = q.where(Payment.created_at >= start, Payment.created_at < end)
    if method:
        q = q.where(Payment.method == method)
    if staff_id:
        q = q.where(Payment.staff_id == staff_id)
    if device_id:
        q = q.where(Payment.device_id == device_id)
    rows = (await uow.session.execute(q.order_by(Payment.created_at.desc()).limit(limit))).all()
    staff = dict(
        (await uow.session.execute(select(Staff.id, Staff.name).where(Staff.venue_id == venue.id))).all()
    )
    devices = dict(
        (await uow.session.execute(select(Device.id, Device.name).where(Device.venue_id == venue.id))).all()
    )
    order_ids = {o.id for _, o in rows}
    invoices = dict(
        (
            await uow.session.execute(
                select(Invoice.order_id, Invoice.number).where(Invoice.order_id.in_(order_ids))
            )
        ).all()
    )
    lines: list[dict[str, Any]] = []
    for p, o in rows:
        sign = -1 if p.kind == "refund" else 1
        lines.append(
            {
                "id": p.id,
                "ref": p.id[-8:],  # short reference printed and spoken ("payment 4F2K9QZA")
                "at": (p.completed_at or p.created_at).isoformat(),
                "kind": p.kind,
                "status": p.status,
                "method": p.method,
                "amount": p.amount * sign,
                "tendered": p.tendered,
                "change_given": p.change_given,
                "order_id": o.id,
                "token": o.token,
                "table": o.table_ref,
                "channel": o.channel,
                "collected_by": staff.get(p.staff_id or "")
                or ("Guest (self-service)" if not p.staff_id else None),
                "staff_id": p.staff_id,
                "device": devices.get(p.device_id or ""),
                "outside_ref": p.external_ref or p.gateway_ref,
                "invoice": invoices.get(o.id),
                "shift_id": p.shift_id,
                "reason": p.reason,
            }
        )
    ok = [x for x in lines if x["status"] == "succeeded"]
    by_method: dict[str, int] = {}
    by_staff: dict[str, int] = {}
    for x in ok:
        m, who, amt = str(x["method"]), str(x["collected_by"] or "?"), int(x["amount"])
        by_method[m] = by_method.get(m, 0) + amt
        by_staff[who] = by_staff.get(who, 0) + amt
    return {
        "day": day,
        "lines": lines,
        "total": sum(x["amount"] for x in ok),
        "count": len(ok),
        "by_method": by_method,
        "by_staff": by_staff,
    }
