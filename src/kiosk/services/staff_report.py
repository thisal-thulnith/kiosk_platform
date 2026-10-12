"""Who did what, for the owner: orders each person took, what they sold, the payments they collected,
the guest calls they went to (and how fast), the food they took to tables, voids and cash differences.
Plus the same view per table. Everything comes from the order event log, payments, calls and shifts."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select

from kiosk.infra.models import CashShift, Order, OrderEvent, Payment, ServiceRequest, Staff, Venue, utcnow
from kiosk.services.menu import local_now
from kiosk.services.uow import UnitOfWork

GUEST = "guest"  # orders and payments nobody on staff touched (kiosk, table, QR on the guest's phone)


def _avg(xs: list[float]) -> int | None:
    return round(mean(xs)) if xs else None


def _row(name: str, role: str) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "orders_taken": 0,
        "rounds_added": 0,
        "items_ordered": 0,
        "value_ordered": 0,
        "payments": {"count": 0, "amount": 0, "by_method": defaultdict(int)},
        "calls": {"answered": 0, "answer_seconds": [], "done_seconds": []},
        "served": {"count": 0, "seconds": []},
        "tables": set(),
        "voids": 0,
        "cancels": 0,
        "shifts": {"count": 0, "variance": 0},
    }


async def staff_report(uow: UnitOfWork, venue: Venue, start: date, end: date) -> dict[str, Any]:
    s = uow.session
    orders = (
        await s.scalars(
            select(Order).where(
                Order.venue_id == venue.id,
                Order.business_date >= start.isoformat(),
                Order.business_date <= end.isoformat(),
            )
        )
    ).all()
    by_id = {o.id: o for o in orders}
    ids = list(by_id) or [""]
    tz = local_now(venue, utcnow()).tzinfo
    lo = datetime.combine(start, datetime.min.time(), tzinfo=tz)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz)

    staff = {st.id: st for st in (await s.scalars(select(Staff).where(Staff.venue_id == venue.id))).all()}
    rows: dict[str, dict[str, Any]] = {}

    def row(staff_id: str | None) -> dict[str, Any]:
        key = staff_id if staff_id in staff else GUEST
        if key not in rows:
            st = staff.get(key)
            rows[key] = _row(st.name, st.role) if st else _row("Guest (self-service)", "guest")
        return rows[key]

    events = (
        await s.scalars(
            select(OrderEvent).where(
                OrderEvent.order_id.in_(ids),
                OrderEvent.type.in_(
                    ["order.created", "order.round_added", "order.served", "order.voided", "order.cancelled"]
                ),
            )
        )
    ).all()
    for e in events:
        o = by_id[e.order_id]
        r = row(e.staff_id)
        if o.table_ref and e.staff_id:
            r["tables"].add(o.table_ref)
        if e.type == "order.created":
            r["orders_taken"] += 1
            if o.payment_status in ("paid", "refunded") or o.is_tab:
                r["value_ordered"] += o.total
            r["items_ordered"] += sum(i.quantity for i in o.items if i.kds_status != "voided")
        elif e.type == "order.round_added":
            r["rounds_added"] += 1
        elif e.type == "order.served":
            r["served"]["count"] += 1
            if o.ready_at and _aware(o.ready_at) <= _aware(e.created_at):
                r["served"]["seconds"].append((_aware(e.created_at) - _aware(o.ready_at)).total_seconds())
        elif e.type == "order.voided":
            r["voids"] += 1
        elif e.type == "order.cancelled" and e.staff_id:
            r["cancels"] += 1

    pays = (
        await s.scalars(select(Payment).where(Payment.order_id.in_(ids), Payment.status == "succeeded"))
    ).all()
    for p in pays:
        r = row(p.staff_id)
        amount = -p.amount if p.kind == "refund" else p.amount
        r["payments"]["count"] += 1
        r["payments"]["amount"] += amount
        r["payments"]["by_method"][p.method] += amount
        paid_for = by_id.get(p.order_id)
        if paid_for and paid_for.table_ref and p.staff_id:
            r["tables"].add(paid_for.table_ref)

    calls = (
        await s.scalars(
            select(ServiceRequest).where(
                ServiceRequest.venue_id == venue.id,
                ServiceRequest.created_at >= lo,
                ServiceRequest.created_at < hi,
            )
        )
    ).all()
    unanswered = 0
    for c in calls:
        if not c.acknowledged_by:
            unanswered += c.status != "done"
            continue
        r = row(c.acknowledged_by)
        r["calls"]["answered"] += 1
        if c.acknowledged_at:
            ack = _aware(c.acknowledged_at)
            r["calls"]["answer_seconds"].append((ack - _aware(c.created_at)).total_seconds())
            if c.done_at:
                r["calls"]["done_seconds"].append((_aware(c.done_at) - ack).total_seconds())
        if c.table_ref:
            r["tables"].add(c.table_ref)

    shifts = (
        await s.scalars(
            select(CashShift).where(
                CashShift.venue_id == venue.id, CashShift.opened_at >= lo, CashShift.opened_at < hi
            )
        )
    ).all()
    for sh in shifts:
        r = row(sh.opened_by)
        r["shifts"]["count"] += 1
        r["shifts"]["variance"] += sh.variance or 0

    people = []
    for key, r in rows.items():
        ans, done = r["calls"].pop("answer_seconds"), r["calls"].pop("done_seconds")
        srv = r["served"].pop("seconds")
        r["calls"]["avg_answer_seconds"] = _avg(ans)
        r["calls"]["slowest_answer_seconds"] = round(max(ans)) if ans else None
        r["calls"]["avg_to_done_seconds"] = _avg(done)
        r["served"]["avg_seconds"] = _avg(srv)
        r["payments"]["by_method"] = dict(r["payments"]["by_method"])
        r["table_visits"] = r["calls"]["answered"] + r["served"]["count"]
        r["tables"] = sorted(r["tables"])
        people.append({"staff_id": None if key == GUEST else key, **r})
    people.sort(key=lambda r: (r["staff_id"] is None, -r["payments"]["amount"], -r["orders_taken"]))

    tables: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"orders": 0, "revenue": 0, "calls": 0, "answer_seconds": [], "waiters": set()}
    )
    for o in orders:
        if not o.table_ref:
            continue
        t = tables[o.table_ref]
        t["orders"] += 1
        if o.payment_status == "paid":
            t["revenue"] += o.total
    for c in calls:
        if not c.table_ref:
            continue
        t = tables[c.table_ref]
        t["calls"] += 1
        if c.acknowledged_at:
            t["answer_seconds"].append((_aware(c.acknowledged_at) - _aware(c.created_at)).total_seconds())
        if c.acknowledged_by in staff:
            t["waiters"].add(staff[c.acknowledged_by].name)
    table_rows = []
    for ref, t in sorted(tables.items()):
        secs = t.pop("answer_seconds")
        table_rows.append(
            {
                "table_ref": ref,
                **t,
                "waiters": sorted(t["waiters"]),
                "avg_answer_seconds": _avg(secs),
                "average_bill": round(t["revenue"] / t["orders"]) if t["orders"] else 0,
            }
        )
    all_answers = [
        (_aware(c.acknowledged_at) - _aware(c.created_at)).total_seconds() for c in calls if c.acknowledged_at
    ]
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "staff": people,
        "tables": table_rows,
        "calls": {"count": len(calls), "unanswered": unanswered, "avg_answer_seconds": _avg(all_answers)},
    }


def _aware(dt: datetime) -> datetime:
    """SQLite gives naive datetimes back; they are UTC."""
    from datetime import UTC

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
