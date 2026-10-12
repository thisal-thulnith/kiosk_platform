"""Loyalty (R-LOYAL): phone-number members, points, tiers with automatic discounts, "your usual".

Kept only with the guest's consent (PDPA No. 9 of 2022): the consent text and time are stored,
guests see only their first name, and a member can be forgotten (anonymised) on request.
"""

import re
from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from kiosk.errors import AppError
from kiosk.infra.models import Customer, Order, Venue, utcnow
from kiosk.services.menu import Discount
from kiosk.services.plans import require_module
from kiosk.services.uow import UnitOfWork


def normalize_phone(raw: str) -> str:
    """Sri Lankan numbers to E.164: 0771234567 / 771234567 / +94 77 123 4567 -> +94771234567."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+"):
        num = digits[1:]
    elif digits.startswith("0") and len(digits) == 10:
        num = "94" + digits[1:]
    elif len(digits) == 9:
        num = "94" + digits
    else:
        num = digits
    if not num.isdigit() or not 10 <= len(num) <= 15:
        raise AppError("bad_phone", "Enter a mobile number, e.g. 077 123 4567")
    return "+" + num


def tier_for(venue: Venue, lifetime: int) -> dict[str, Any] | None:
    tiers = sorted(venue.setting("loyalty_tiers") or [], key=lambda t: t["min_points"])
    best = None
    for t in tiers:
        if lifetime >= int(t["min_points"]):
            best = t
    return best


def discount_for(venue: Venue, customer: Customer) -> Discount | None:
    tier = tier_for(venue, customer.lifetime_points)
    if not tier or not tier.get("discount_bp"):
        return None
    return Discount(int(tier["discount_bp"]), f"{tier['name']} member {int(tier['discount_bp']) / 100:g}%")


async def find(uow: UnitOfWork, venue: Venue, phone: str) -> Customer | None:
    require_module(venue, "R-LOYAL")
    found: Customer | None = await uow.session.scalar(
        select(Customer).where(
            Customer.tenant_id == venue.tenant_id, Customer.phone == normalize_phone(phone)
        )
    )
    return found


async def join(uow: UnitOfWork, venue: Venue, phone: str, name: str | None, consent: bool) -> Customer:
    if not consent:
        raise AppError("consent_required", "Please agree to the member terms to join")
    customer = await find(uow, venue, phone)
    if customer is None:
        customer = Customer(tenant_id=venue.tenant_id, phone=normalize_phone(phone))
        uow.session.add(customer)
    customer.name = (name or "").strip()[:120] or customer.name
    customer.consent_at = utcnow()
    customer.consent_text = str(venue.setting("loyalty_consent_text"))[:500]
    await uow.session.flush()
    return customer


async def favorites(uow: UnitOfWork, customer: Customer, top: int = 3) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(days=90)
    orders = (
        await uow.session.scalars(
            select(Order).where(
                Order.customer_id == customer.id, Order.payment_status == "paid", Order.created_at >= since
            )
        )
    ).all()
    counts: Counter[str] = Counter()
    names: dict[str, Any] = {}
    for o in orders:
        for i in o.items:
            if i.parent_position is None:
                counts[i.menu_item_id] += i.quantity
                names[i.menu_item_id] = i.name
    return [{"menu_item_id": m, "name": names[m]} for m, _ in counts.most_common(top)]


async def summary(uow: UnitOfWork, venue: Venue, customer: Customer) -> dict[str, Any]:
    """What a guest screen may show: first name only, tier, points, their usual."""
    tier = tier_for(venue, customer.lifetime_points)
    tiers = sorted(venue.setting("loyalty_tiers") or [], key=lambda t: t["min_points"])
    nxt = next((t for t in tiers if int(t["min_points"]) > customer.lifetime_points), None)
    return {
        "known": True,
        "first_name": (customer.name or "").split(" ")[0] or None,
        "tier": tier["name"] if tier else None,
        "discount_bp": int(tier["discount_bp"]) if tier else 0,
        "points": customer.points,
        "next_tier": {"name": nxt["name"], "points_needed": int(nxt["min_points"]) - customer.lifetime_points}
        if nxt
        else None,
        "favorites": await favorites(uow, customer),
    }


def earn(venue: Venue, order: Order, customer: Customer) -> int:
    """Points for a paid order: per Rs 100 actually paid (after the member discount)."""
    points = (order.total // 10_000) * int(venue.setting("loyalty_points_per_100"))
    customer.points += points
    customer.lifetime_points += points
    customer.visits += 1
    customer.last_visit_at = utcnow()
    order.points_earned = points
    return points


def reverse(order: Order, customer: Customer) -> None:
    """A refunded order gives its points back."""
    customer.points = max(0, customer.points - order.points_earned)
    customer.lifetime_points = max(0, customer.lifetime_points - order.points_earned)
    order.points_earned = 0


def forget(customer: Customer) -> None:
    """PDPA delete-on-request: remove what identifies the person, keep anonymous sales history."""
    customer.phone = None
    customer.name = None
    customer.consent_at = None
    customer.consent_text = None
    customer.points = 0
    customer.forgotten_at = utcnow()


def admin_dict(c: Customer, venue: Venue) -> dict[str, Any]:
    tier = tier_for(venue, c.lifetime_points)
    return {
        "id": c.id,
        "phone": c.phone,
        "name": c.name,
        "tier": tier["name"] if tier else None,
        "points": c.points,
        "lifetime_points": c.lifetime_points,
        "visits": c.visits,
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        "consent_at": c.consent_at.isoformat() if c.consent_at else None,
        "forgotten": c.forgotten_at is not None,
    }
