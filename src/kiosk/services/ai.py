"""AI Autonomous Mode, levels 0-3 (Full Plan ladder), from the venue's own data.

What each level does (all levels keep prices unchanged, and allergens, emergencies and refunds
never depend on AI):

  1  Insights for staff and the owner: kitchen load, slow items to pause, strong pairings.
  2  Upsell to guests: "guests who ordered X also ordered Y", learned from paid orders.
  3  Screens reorder: best sellers for this time of day first, and when the kitchen is busy,
     quick items are highlighted, slow ones marked, and the shown wait time goes up.

  4  Clear perishable stock (needs R-INV): when plenty is left close to its use-by time, propose a
     discount within the owner's cap (ai_price_cap_bp). Discounts only, never a price rise; by
     default the owner approves each one first (ai_requires_approval).

Every change in what screens are told is logged as an AiAction with its reason. Switching the
venue to Manual mode (or level 0) turns all of it off at once.
"""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select

from kiosk.domain.orders import congestion
from kiosk.infra.models import AiAction, MenuItem, Order, PriceOffer, StockItem, Venue, utcnow
from kiosk.services.menu import COMBO_STATION, local_now
from kiosk.services.uow import UnitOfWork

HISTORY_DAYS = 30
FAST_MINUTES = 8
SLOW_MINUTES = 15
OFFER_WINDOW = timedelta(hours=2)  # look at stock whose use-by time is this close


async def _history(uow: UnitOfWork, venue: Venue) -> list[Order]:
    since = utcnow() - timedelta(days=HISTORY_DAYS)
    rows = (
        await uow.session.scalars(
            select(Order).where(
                Order.venue_id == venue.id, Order.created_at >= since, Order.payment_status == "paid"
            )
        )
    ).all()
    return list(rows)


def pairings(orders: list[Order], min_support: int = 2, top: int = 3) -> dict[str, list[str]]:
    """For each item, the items most often in the same paid order (combo parts excluded)."""
    together: dict[str, Counter[str]] = defaultdict(Counter)
    for o in orders:
        ids = {i.menu_item_id for i in o.items if i.parent_position is None and i.station != COMBO_STATION}
        for a in ids:
            for b in ids - {a}:
                together[a][b] += 1
    return {a: [b for b, n in c.most_common(top) if n >= min_support] for a, c in together.items() if c}


def cook_minutes(orders: list[Order], items: list[MenuItem], default: int) -> dict[str, float]:
    """Typical cooking time per item: measured start->done where we have it, else the menu value."""
    seen: dict[str, list[float]] = defaultdict(list)
    for o in orders:
        for i in o.items:
            if i.started_at and i.done_at and i.done_at > i.started_at:
                seen[i.menu_item_id].append((i.done_at - i.started_at).total_seconds() / 60)
    return {
        m.id: round(mean(seen[m.id]), 1) if seen.get(m.id) else float(m.prep_minutes or default)
        for m in items
    }


def best_for_hour(orders: list[Order], venue: Venue, hour: int, top: int = 3) -> list[str]:
    counts: Counter[str] = Counter()
    for o in orders:
        h = local_now(venue, o.created_at).hour
        if abs(h - hour) <= 1:
            for i in o.items:
                if i.parent_position is None:
                    counts[i.menu_item_id] += i.quantity
    return [m for m, _ in counts.most_common(top)]


async def compute_policy(uow: UnitOfWork, venue: Venue, load: dict[str, Any]) -> dict[str, Any]:
    mode, level = venue.setting("mode"), int(venue.setting("ai_level"))
    active = 0 if mode != "ai" else level
    off = {
        "mode": mode,
        "level": active,
        "active": False,
        "highlights": [],
        "fast": [],
        "slow": [],
        "upsell": {},
    }
    if active == 0:
        return {**off, "insights": [], "wait_extra_minutes": 0, "reasons": []}
    orders = await _history(uow, venue)
    items = list(
        (
            await uow.session.scalars(
                select(MenuItem).where(MenuItem.venue_id == venue.id, MenuItem.is_active)
            )
        ).all()
    )
    names = {m.id: m.name.get("en", m.id) for m in items}
    default = int(venue.setting("default_prep_minutes"))
    cook = cook_minutes(orders, items, default)
    fast = [m.id for m in items if cook.get(m.id, default) <= FAST_MINUTES and not m.combo_slots]
    slow = [m.id for m in items if cook.get(m.id, default) >= SLOW_MINUTES]
    busy = load.get("level") in ("busy", "overloaded")
    pairs = pairings(orders)

    insights, reasons = [], []
    if busy:
        insights.append(
            f"Kitchen is {load['level']} ({load['open_tickets']} open, {load['score_minutes']} min load)."
            + (f" Consider pausing slow items: {', '.join(names[i] for i in slow[:4])}." if slow else "")
        )
    for a, bs in list(pairs.items())[:3]:
        if bs:
            insights.append(
                f"{names.get(a, a)} is often ordered with {', '.join(names.get(b, b) for b in bs)}."
            )
    if not orders:
        insights.append("Not enough sales yet: suggestions get better after a few weeks of orders.")

    policy: dict[str, Any] = {**off, "active": True, "insights": insights}
    if active >= 2:
        policy["upsell"] = {a: bs for a, bs in pairs.items() if bs}
        if policy["upsell"]:
            reasons.append("Upsell from items bought together in the last 30 days")
    if active >= 3:
        hour = local_now(venue, utcnow()).hour
        best = best_for_hour(orders, venue, hour)
        quick = fast[:4] if busy else []
        policy["highlights"] = quick + [b for b in best if b not in quick]
        policy["fast"] = fast if busy else []
        policy["slow"] = slow if busy else []
        if best:
            reasons.append(f"Best sellers around {hour:02d}:00 shown first")
        if busy:
            reasons.append(f"Kitchen {load['level']}: quick items first, slow items marked")
    extra = 0
    if active >= 3 and load.get("level") == "overloaded":
        extra = 10
    elif active >= 3 and busy:
        extra = 5
    policy["wait_extra_minutes"] = extra
    if active >= 4:
        made = await propose_offers(uow, venue, names)
        if made:
            reasons.append(f"{made} deal(s) proposed to clear stock before its use-by time")
    policy["reasons"] = reasons
    await _log_if_changed(uow, venue, policy)
    return policy


async def _log_if_changed(uow: UnitOfWork, venue: Venue, policy: dict[str, Any]) -> None:
    shown = {k: policy[k] for k in ("level", "highlights", "fast", "slow", "upsell", "wait_extra_minutes")}
    digest = hashlib.sha256(json.dumps(shown, sort_keys=True).encode()).hexdigest()[:16]
    last = await uow.session.scalar(
        select(AiAction)
        .where(AiAction.venue_id == venue.id, AiAction.kind == "policy")
        .order_by(AiAction.created_at.desc())
        .limit(1)
    )
    if last is None or last.data.get("digest") != digest:
        uow.session.add(
            AiAction(
                venue_id=venue.id,
                kind="policy",
                data={"digest": digest, **shown},
                reason="; ".join(policy["reasons"]) or "AI mode on, nothing to change",
            )
        )
        await uow.session.commit()


def offer_bp(cap_bp: int, minutes_left: float) -> int:
    """Bigger discount the closer the use-by time: full cap in the last hour, half before that."""
    bp = cap_bp if minutes_left <= 60 else cap_bp // 2
    return max(0, min(cap_bp, bp // 100 * 100))


async def propose_offers(uow: UnitOfWork, venue: Venue, names: dict[str, str]) -> int:
    """Level 4: one offer per perishable item with plenty left near its use-by time."""
    now = utcnow()
    cap = max(0, min(int(venue.setting("ai_price_cap_bp")), 5000))
    stock = (
        await uow.session.scalars(
            select(StockItem).where(
                StockItem.venue_id == venue.id,
                StockItem.perishable_until.is_not(None),
                StockItem.perishable_until > now,
                StockItem.perishable_until <= now + OFFER_WINDOW,
            )
        )
    ).all()
    open_offers = {
        o.menu_item_id
        for o in (
            await uow.session.scalars(
                select(PriceOffer).where(PriceOffer.venue_id == venue.id, PriceOffer.ends_at > now)
            )
        ).all()
    }
    made = 0
    for s in stock:
        if s.menu_item_id in open_offers or s.menu_item_id not in names or s.on_hand <= max(s.low_at, 1) * 2:
            continue
        assert s.perishable_until is not None
        left = (s.perishable_until - now).total_seconds() / 60
        bp = offer_bp(cap, left)
        if bp == 0:
            continue
        approval = bool(venue.setting("ai_requires_approval"))
        reason = (
            f"{s.on_hand} {names[s.menu_item_id]} left, use by "
            f"{local_now(venue, s.perishable_until):%H:%M}: {bp / 100:g}% off (cap {cap / 100:g}%)"
        )
        offer = PriceOffer(
            venue_id=venue.id,
            menu_item_id=s.menu_item_id,
            discount_bp=bp,
            status="proposed" if approval else "active",
            reason=reason,
            starts_at=None if approval else now,
            ends_at=s.perishable_until,
            decided_by=None if approval else "AI (no approval needed)",
        )
        uow.session.add(offer)
        uow.session.add(
            AiAction(
                venue_id=venue.id,
                kind="offer",
                data={"menu_item_id": s.menu_item_id, "discount_bp": bp, "status": offer.status},
                reason=reason,
            )
        )
        made += 1
    if made:
        if not bool(venue.setting("ai_requires_approval")):
            venue.config_version += 1  # live deals reach the restaurant's hub
        await uow.session.commit()
    return made


def offer_dict(o: PriceOffer, names: dict[str, str], prices: dict[str, int]) -> dict[str, Any]:
    now = utcnow()
    status = "expired" if o.status in ("proposed", "active") and o.ends_at <= now else o.status
    price = prices.get(o.menu_item_id, 0)
    return {
        "id": o.id,
        "menu_item_id": o.menu_item_id,
        "name": names.get(o.menu_item_id, o.menu_item_id),
        "price": price,
        "offer_price": price - price * o.discount_bp // 10_000,
        "discount_bp": o.discount_bp,
        "status": status,
        "reason": o.reason,
        "ends_at": o.ends_at.isoformat(),
        "decided_by": o.decided_by,
    }


def kitchen_level(open_tickets: int, avg_seconds: float, venue: Venue) -> dict[str, Any]:
    load = congestion(
        open_tickets,
        avg_seconds,
        int(venue.setting("kitchen_cooks")),
        int(venue.setting("kds_warn_minutes")),
        int(venue.setting("kds_late_minutes")),
    )
    return {"open_tickets": open_tickets, **load}
