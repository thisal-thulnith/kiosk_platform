"""Guest feedback after eating: stars, quick tags, a comment. Staff see it at once (a low rating
needs someone to go to the table); the owner sees it per day, per tag and per waiter."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select

from kiosk.errors import AppError, NotFound
from kiosk.infra.models import Feedback, Order, OrderEvent, Staff, Venue, utcnow
from kiosk.services.menu import local_now
from kiosk.services.uow import Actor, UnitOfWork

TAGS = ("food", "service", "speed", "value", "clean", "slow", "cold", "wrong_order")
LOW = 2  # this many stars or fewer: tell staff loudly


def feedback_dict(f: Feedback, names: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": f.id,
        "rating": f.rating,
        "tags": f.tags or [],
        "comment": f.comment,
        "table_ref": f.table_ref,
        "order_id": f.order_id,
        "low": f.rating <= LOW,
        "created_at": f.created_at.isoformat(),
        "seen": f.seen_at is not None,
        "seen_by": (names or {}).get(f.seen_by or "") if f.seen_by else None,
    }


async def give(
    uow: UnitOfWork,
    venue: Venue,
    actor: Actor,
    table_ref: str | None,
    order_id: str | None,
    rating: int,
    tags: list[str],
    comment: str | None,
) -> Feedback:
    if not 1 <= rating <= 5:
        raise AppError("bad_rating", "Rating must be 1 to 5 stars")
    unknown = set(tags) - set(TAGS)
    if unknown:
        raise AppError("bad_tags", f"Unknown tags: {', '.join(sorted(unknown))}")
    if order_id:
        order = await uow.session.get(Order, order_id)
        if order is None or order.venue_id != venue.id:
            raise NotFound("Order")
        table_ref = table_ref or order.table_ref
        # One feedback per order: giving it again changes it.
        existing = await uow.session.scalar(select(Feedback).where(Feedback.order_id == order_id))
        if existing is not None:
            existing.rating, existing.tags, existing.comment = rating, tags, comment
            existing.seen_at = existing.seen_by = None
            _announce(uow, venue, existing)
            return existing
    f = Feedback(
        venue_id=venue.id,
        device_id=actor.device_id,
        table_ref=table_ref,
        order_id=order_id,
        rating=rating,
        tags=tags,
        comment=(comment or "").strip()[:500] or None,
    )
    uow.session.add(f)
    await uow.session.flush()
    _announce(uow, venue, f)
    return f


def _announce(uow: UnitOfWork, venue: Venue, f: Feedback) -> None:
    uow.emit(venue.id, "feedback.new", {"feedback": feedback_dict(f)}, ["orders", "service"])


async def recent(uow: UnitOfWork, venue: Venue, hours: int = 12) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(hours=hours)
    rows = (
        await uow.session.scalars(
            select(Feedback)
            .where(Feedback.venue_id == venue.id, Feedback.created_at >= since)
            .order_by(Feedback.created_at.desc())
        )
    ).all()
    who = await staff_names(uow, venue)
    return [feedback_dict(f, who) for f in rows]


async def mark_seen(uow: UnitOfWork, venue: Venue, feedback_id: str, actor: Actor) -> Feedback:
    f = await uow.session.get(Feedback, feedback_id)
    if f is None or f.venue_id != venue.id:
        raise NotFound("Feedback")
    f.seen_at, f.seen_by = utcnow(), actor.staff_id
    uow.emit(
        venue.id,
        "feedback.seen",
        {"feedback": feedback_dict(f, await staff_names(uow, venue))},
        ["orders", "service"],
    )
    return f


async def staff_names(uow: UnitOfWork, venue: Venue) -> dict[str, str]:
    rows = (await uow.session.execute(select(Staff.id, Staff.name).where(Staff.venue_id == venue.id))).all()
    return {str(k): str(v) for k, v in rows}


async def report(uow: UnitOfWork, venue: Venue, start: datetime, end: datetime) -> dict[str, Any]:
    """Average stars, how many of each, what guests mention, and per waiter (who served the order)."""
    rows = (
        await uow.session.scalars(
            select(Feedback).where(
                Feedback.venue_id == venue.id, Feedback.created_at >= start, Feedback.created_at < end
            )
        )
    ).all()
    who_names = await staff_names(uow, venue)
    order_ids = [f.order_id for f in rows if f.order_id] or [""]
    served = {
        e.order_id: e.staff_id
        for e in (
            await uow.session.scalars(
                select(OrderEvent).where(
                    OrderEvent.order_id.in_(order_ids), OrderEvent.type == "order.served"
                )
            )
        ).all()
        if e.staff_id
    }
    per: dict[str, list[int]] = defaultdict(list)
    for f in rows:
        who = served.get(f.order_id or "")
        if who:
            per[who_names.get(who, who)].append(f.rating)
    stars = Counter(f.rating for f in rows)
    return {
        "count": len(rows),
        "average": round(mean(f.rating for f in rows), 2) if rows else None,
        "stars": {str(n): stars.get(n, 0) for n in range(5, 0, -1)},
        "tags": dict(Counter(t for f in rows for t in (f.tags or [])).most_common()),
        "low": sum(1 for f in rows if f.rating <= LOW),
        "by_waiter": {k: {"count": len(v), "average": round(mean(v), 2)} for k, v in per.items()},
        "comments": [
            feedback_dict(f, who_names)
            for f in sorted(rows, key=lambda f: f.created_at, reverse=True)
            if f.comment
        ][:50],
    }


def day_range(venue: Venue, start_day: str, end_day: str) -> tuple[datetime, datetime]:
    from datetime import date

    tz = local_now(venue, utcnow()).tzinfo
    lo = datetime.combine(date.fromisoformat(start_day), datetime.min.time(), tzinfo=tz)
    hi = datetime.combine(date.fromisoformat(end_day) + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return lo, hi
