import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api.deps import AdminVenue, Uow
from kiosk.errors import AppError
from kiosk.infra.models import Invoice, Order, OrderEvent, Payment, ServiceRequest, utcnow
from kiosk.services.menu import local_now

router = APIRouter(prefix="/v1/admin/venues/{venue_id}/reports", tags=["admin: reports"])

SOLD = ("in_kitchen", "ready", "completed")


async def _orders(uow: Uow, venue_id: str, start: date, end: date) -> list[Order]:
    if end < start:
        raise AppError("bad_range", "'to' must not be before 'from'")
    if (end - start).days > 366:
        raise AppError("bad_range", "Range is limited to one year")
    rows = (
        await uow.session.scalars(
            select(Order).where(
                Order.venue_id == venue_id,
                Order.business_date >= start.isoformat(),
                Order.business_date <= end.isoformat(),
            )
        )
    ).all()
    return list(rows)


@router.get("/kitchen-load")
async def kitchen(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """Live kitchen congestion (open tickets x average prep time / cooks)."""
    from kiosk.api.routers.kds import kitchen_load

    return await kitchen_load(uow, venue)


@router.get("/sales")
async def sales(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> dict[str, Any]:
    """Sales for business dates in [from, to] (venue local dates). Defaults to today."""
    today = local_now(venue, utcnow()).date()
    start, end = from_ or today, to or today
    orders = await _orders(uow, venue.id, start, end)

    sold = [o for o in orders if o.status in SOLD and o.payment_status == "paid"]
    by_channel: dict[str, dict[str, int]] = defaultdict(lambda: {"orders": 0, "total": 0})
    by_hour: dict[int, dict[str, int]] = defaultdict(lambda: {"orders": 0, "total": 0})
    top: Counter[str] = Counter()
    revenue: Counter[str] = Counter()
    tax: Counter[str] = Counter()
    prep: list[float] = []
    for o in sold:
        by_channel[o.channel]["orders"] += 1
        by_channel[o.channel]["total"] += o.total
        hour = local_now(venue, o.created_at).hour
        by_hour[hour]["orders"] += 1
        by_hour[hour]["total"] += o.total
        for t in o.tax_lines:
            tax[t["code"]] += t["amount"]
        for i in o.items:
            if i.kds_status == "voided":
                continue
            name = i.name.get("en", i.menu_item_id)
            top[name] += i.quantity
            revenue[name] += i.line_total
        if o.released_at and o.ready_at:
            prep.append((o.ready_at - o.released_at).total_seconds())

    payments: dict[str, dict[str, int]] = defaultdict(lambda: {"charges": 0, "refunds": 0})
    order_ids = [o.id for o in orders]
    if order_ids:
        for p in (
            await uow.session.scalars(
                select(Payment).where(Payment.order_id.in_(order_ids), Payment.status == "succeeded")
            )
        ).all():
            payments[p.method]["refunds" if p.kind == "refund" else "charges"] += p.amount

    status_counts = Counter(o.status for o in orders)
    gross = sum(o.total for o in sold)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "orders": len(sold),
        "gross_total": gross,
        "subtotal": sum(o.subtotal for o in sold),
        "tax_by_code": dict(tax),
        "average_bill": round(gross / len(sold)) if sold else 0,
        "by_channel": dict(by_channel),
        "by_hour": {f"{h:02d}:00": v for h, v in sorted(by_hour.items())},
        "payments": dict(payments),
        "top_items": [{"name": n, "quantity": q, "revenue": revenue[n]} for n, q in top.most_common(20)],
        "avg_prep_seconds": round(mean(prep)) if prep else None,
        "status_counts": dict(status_counts),
        "refunded_orders": sum(1 for o in orders if o.payment_status == "refunded"),
    }


@router.get("/orders.csv")
async def orders_csv(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> StreamingResponse:
    """One row per order, for accounting."""
    end = to or local_now(venue, utcnow()).date()
    start = from_ or end - timedelta(days=30)
    orders = sorted(await _orders(uow, venue.id, start, end), key=lambda o: o.created_at)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "business_date",
            "token",
            "order_id",
            "channel",
            "table",
            "status",
            "payment_status",
            "subtotal",
            "tax_total",
            "total",
            "paid_total",
            "created_at",
        ]
    )
    for o in orders:
        w.writerow(
            [
                o.business_date,
                o.token,
                o.id,
                o.channel,
                o.table_ref or "",
                o.status,
                o.payment_status,
                f"{o.subtotal / 100:.2f}",
                f"{o.tax_total / 100:.2f}",
                f"{o.total / 100:.2f}",
                f"{o.paid_total / 100:.2f}",
                o.created_at.isoformat(),
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="orders-{start}-{end}.csv"'},
    )


# ------------------------------------------------------------------ tax ledger (accounting / IRD)


@router.get("/tax-ledger.csv")
async def tax_ledger(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> StreamingResponse:
    """One row per invoice with every tax and charge in its own column (service charge, VAT, SSCL...).

    Invoices are never edited after payment; refunds appear as their own columns. The column layout
    is a clean base for RAMIS returns; confirm the exact upload format with your tax adviser.
    """
    end = to or local_now(venue, utcnow()).date()
    start = from_ or end - timedelta(days=30)
    orders = {o.id: o for o in await _orders(uow, venue.id, start, end)}
    invoices = (
        await uow.session.scalars(
            select(Invoice).where(Invoice.venue_id == venue.id, Invoice.order_id.in_(list(orders) or [""]))
        )
    ).all()
    codes = sorted({t["code"] for o in orders.values() for t in o.tax_lines})
    buf = io.StringIO()
    w = csv.writer(buf)
    head = [
        "invoice_number",
        "issued_at_local",
        "business_date",
        "order_token",
        "channel",
        "subtotal",
        "discount",
    ]
    w.writerow(head + [f"tax_{c}" for c in codes] + ["total", "paid_by", "refunded", "refund_total"])
    for inv in sorted(invoices, key=lambda i: i.number):
        o = orders[inv.order_id]
        taxes = {t["code"]: t["amount"] for t in o.tax_lines}
        charges = [p for p in o.payments if p.kind == "charge" and p.status == "succeeded"]
        refunds = [p for p in o.payments if p.kind == "refund" and p.status == "succeeded"]
        w.writerow(
            [
                inv.number,
                local_now(venue, inv.issued_at).strftime("%Y-%m-%d %H:%M:%S"),
                o.business_date,
                o.token,
                o.channel,
                f"{o.subtotal / 100:.2f}",
                f"{o.discount_total / 100:.2f}",
                *[f"{taxes.get(c, 0) / 100:.2f}" for c in codes],
                f"{inv.total / 100:.2f}",
                ";".join(sorted({p.method for p in charges})),
                "Y" if refunds else "N",
                f"{sum(p.amount for p in refunds) / 100:.2f}",
            ]
        )
    buf.seek(0)
    name = f"tax-ledger-{venue.code}-{start}-{end}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


# ------------------------------------------------------------------ reconciliation


async def _day_payments(uow: Uow, venue: AdminVenue, day: date) -> list[Payment]:
    orders = await _orders(uow, venue.id, day, day)
    return [p for o in orders for p in o.payments]


@router.get("/reconciliation")
async def reconciliation(venue: AdminVenue, uow: Uow, day: date | None = None) -> dict[str, Any]:
    """What each payment method should add up to for a business day, and anything that needs a look."""
    day = day or local_now(venue, utcnow()).date()
    pays = await _day_payments(uow, venue, day)
    by_method: dict[str, dict[str, int]] = defaultdict(lambda: {"charges": 0, "refunds": 0, "count": 0})
    for p in pays:
        if p.status != "succeeded":
            continue
        m = by_method[p.method]
        m["refunds" if p.kind == "refund" else "charges"] += p.amount
        m["count"] += 1
    stale = utcnow() - timedelta(minutes=15)
    attention = [
        {
            "payment_id": p.id,
            "method": p.method,
            "amount": p.amount,
            "issue": "still pending after 15 minutes",
        }
        for p in pays
        if p.status == "pending" and p.created_at < stale
    ] + [
        {"payment_id": p.id, "method": p.method, "amount": p.amount, "issue": f"auto refund: {p.reason}"}
        for p in pays
        if p.kind == "refund" and p.reason and p.reason.startswith("Late or duplicate")
    ]
    return {
        "day": day.isoformat(),
        "by_method": {k: {**v, "net": v["charges"] - v["refunds"]} for k, v in by_method.items()},
        "attention": attention,
    }


class BankRow(BaseModel):
    reference: str = Field(min_length=1, max_length=120, description="The processor's payment reference")
    amount: int = Field(description="LKR cents; negative for refunds")


class BankFile(BaseModel):
    day: date | None = None
    rows: list[BankRow]


@router.post("/reconciliation/match")
async def reconcile(body: BankFile, venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """Match the bank / gateway settlement file against our LankaQR and card-terminal payments.

    Returns matched rows, amount mismatches, payments the bank does not have, and bank rows we
    don't know. Cash and manually keyed card payments are not in a settlement file.
    """
    day = body.day or local_now(venue, utcnow()).date()
    ours = {
        p.gateway_ref: p
        for p in await _day_payments(uow, venue, day)
        if p.gateway_ref and p.status == "succeeded" and p.kind == "charge"
    }
    matched: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in body.rows:
        p = ours.get(row.reference)
        if p is None:
            unknown.append(row.model_dump())
            continue
        seen.add(row.reference)
        entry = {"reference": row.reference, "ours": p.amount, "bank": row.amount, "method": p.method}
        (matched if p.amount == row.amount else mismatch).append(entry)
    missing = [
        {"reference": ref, "ours": p.amount, "method": p.method, "payment_id": p.id}
        for ref, p in ours.items()
        if ref not in seen
    ]
    return {
        "day": day.isoformat(),
        "matched": matched,
        "amount_mismatch": mismatch,
        "missing_in_bank": missing,
        "unknown_in_bank": unknown,
        "all_clear": not (mismatch or missing or unknown),
    }


# ------------------------------------------------------------------ operations


@router.get("/operations")
async def operations(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> dict[str, Any]:
    """Owner KPIs from the Full Plan: late orders, voids, refunds, remakes by reason, kiosk and
    table completion (started vs paid), and how fast staff answer guest calls."""
    today = local_now(venue, utcnow()).date()
    start, end = from_ or today, to or today
    orders = await _orders(uow, venue.id, start, end)
    ids = [o.id for o in orders] or [""]
    events = (
        await uow.session.scalars(
            select(OrderEvent).where(
                OrderEvent.order_id.in_(ids), OrderEvent.type.in_(["kds.remake", "order.voided"])
            )
        )
    ).all()
    remakes: Counter[str] = Counter(e.data.get("reason", "other") for e in events if e.type == "kds.remake")
    void_reasons: Counter[str] = Counter(e.data.get("reason", "") for e in events if e.type == "order.voided")

    kitchen = [o for o in orders if o.promised_at and o.ready_at]
    late = [o for o in kitchen if o.ready_at and o.promised_at and o.ready_at > o.promised_at]
    funnel: dict[str, dict[str, int]] = {}
    for ch in sorted({o.channel for o in orders}):
        mine = [o for o in orders if o.channel == ch]
        paid = sum(1 for o in mine if o.payment_status in ("paid", "refunded"))
        dropped = sum(1 for o in mine if o.status in ("cancelled", "expired"))
        funnel[ch] = {"started": len(mine), "paid": paid, "cancelled_or_expired": dropped}

    lo = datetime.combine(start, datetime.min.time(), tzinfo=local_now(venue, utcnow()).tzinfo)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=lo.tzinfo)
    calls = (
        await uow.session.scalars(
            select(ServiceRequest).where(
                ServiceRequest.venue_id == venue.id,
                ServiceRequest.created_at >= lo,
                ServiceRequest.created_at < hi,
            )
        )
    ).all()
    answered = [(r.acknowledged_at - r.created_at).total_seconds() for r in calls if r.acknowledged_at]
    voided = [o for o in orders if o.status == "voided"]
    refunded = [o for o in orders if o.payment_status == "refunded"]
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "orders": len(orders),
        "late": {
            "count": len(late),
            "of": len(kitchen),
            "percent": round(100 * len(late) / len(kitchen), 1) if kitchen else 0,
        },
        "voids": {"count": len(voided), "value": sum(o.total for o in voided), "reasons": dict(void_reasons)},
        "refunds": {"count": len(refunded), "value": sum(o.total for o in refunded)},
        "remakes": {"count": sum(remakes.values()), "by_reason": dict(remakes)},
        "completion_by_channel": funnel,
        "guest_calls": {
            "count": len(calls),
            "answered": len(answered),
            "avg_answer_seconds": round(mean(answered)) if answered else None,
        },
        "upsell": {
            "items": sum(
                i.quantity
                for o in orders
                if o.payment_status == "paid"
                for i in o.items
                if i.source == "upsell"
            ),
            "revenue": sum(
                i.line_total
                for o in orders
                if o.payment_status == "paid"
                for i in o.items
                if i.source == "upsell"
            ),
        },
        "combos_sold": sum(
            i.quantity for o in orders if o.payment_status == "paid" for i in o.items if i.station == "none"
        ),
    }


# ------------------------------------------------------------------ staff and tables


@router.get("/staff")
async def staff(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> dict[str, Any]:
    """Per person: orders taken, value, payments collected (by way), guest calls answered and how
    fast, food taken to tables, voids, cash differences. Per table: orders, revenue, calls."""
    from kiosk.services.staff_report import staff_report

    today = local_now(venue, utcnow()).date()
    start, end = from_ or today, to or today
    if end < start or (end - start).days > 366:
        raise AppError("bad_range", "Choose a range of up to one year")
    return await staff_report(uow, venue, start, end)


@router.get("/staff.csv")
async def staff_csv(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> StreamingResponse:
    rep = await staff(venue, uow, from_, to)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["name", "role", "orders_taken", "rounds_added", "items_ordered", "value_ordered", "payments",
         "collected", "cash", "card", "qr", "calls_answered", "avg_answer_s", "slowest_answer_s",
         "served", "avg_serve_s", "table_visits", "tables", "voids", "cash_variance"]
    )  # fmt: skip
    for r in rep["staff"]:
        m = r["payments"]["by_method"]
        w.writerow(
            [r["name"], r["role"], r["orders_taken"], r["rounds_added"], r["items_ordered"],
             r["value_ordered"] / 100, r["payments"]["count"], r["payments"]["amount"] / 100,
             m.get("cash", 0) / 100, m.get("card", 0) / 100, m.get("lankaqr", 0) / 100,
             r["calls"]["answered"], r["calls"]["avg_answer_seconds"], r["calls"]["slowest_answer_seconds"],
             r["served"]["count"], r["served"]["avg_seconds"], r["table_visits"], " ".join(r["tables"]),
             r["voids"], r["shifts"]["variance"] / 100]
        )  # fmt: skip
    name = f"staff-{rep['from']}-{rep['to']}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
