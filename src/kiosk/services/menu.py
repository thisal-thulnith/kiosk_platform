from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.domain import tax
from kiosk.domain.menu import in_windows
from kiosk.errors import AppError
from kiosk.infra.models import MenuCategory, MenuItem, PriceOffer, TaxRule, Venue
from kiosk.services.serializers import category_dict, menu_item_dict


def local_now(venue: Venue, at: datetime) -> datetime:
    return at.astimezone(ZoneInfo(venue.timezone))


def offers_on(venue: Venue) -> bool:
    """Deal prices exist only at AI level 4. Manual mode (the kill switch) stops them at once."""
    return venue.setting("mode") == "ai" and int(venue.setting("ai_level")) >= 4


def offer_price(price: int, bp: int) -> int:
    return price - price * bp // 10_000


async def active_offers(session: AsyncSession, venue: Venue, at: datetime) -> dict[str, PriceOffer]:
    if not offers_on(venue):
        return {}
    rows = await session.scalars(
        select(PriceOffer).where(
            PriceOffer.venue_id == venue.id, PriceOffer.status == "active", PriceOffer.ends_at > at
        )
    )
    return {o.menu_item_id: o for o in rows.all() if o.starts_at is None or o.starts_at <= at}


def _with_offer(d: dict[str, Any], offer: PriceOffer | None) -> dict[str, Any]:
    if offer is not None:
        d["offer"] = {
            "price": offer_price(d["price"], offer.discount_bp),
            "discount_bp": offer.discount_bp,
            "ends_at": offer.ends_at.isoformat(),
        }
    return d


async def effective_menu(
    session: AsyncSession, venue: Venue, at: datetime, only_categories: list[str] | None = None
) -> dict[str, Any]:
    """What a screen should show right now: active categories and items in their time windows.

    Items that are out of stock stay in the list with is_available=false so screens can
    show them as sold out.
    """
    now = local_now(venue, at)
    categories = (
        await session.scalars(
            select(MenuCategory)
            .where(MenuCategory.venue_id == venue.id, MenuCategory.is_active)
            .order_by(MenuCategory.sort)
        )
    ).all()
    items = (
        await session.scalars(
            select(MenuItem).where(MenuItem.venue_id == venue.id, MenuItem.is_active).order_by(MenuItem.sort)
        )
    ).all()
    offers = await active_offers(session, venue, at)
    result = []
    for c in categories:
        if not in_windows(c.windows, now):
            continue
        if only_categories and c.id not in only_categories:
            continue
        visible = [
            _with_offer(menu_item_dict(i), offers.get(i.id))
            for i in items
            if i.category_id == c.id and in_windows(i.windows, now)
        ]
        if visible:
            result.append({**category_dict(c), "items": visible})
    # Names of combo parts, so screens can show choices even for parts from other categories.
    part_ids = {
        i for c in result for it in c["items"] for s in it["combo_slots"] for i in s.get("item_ids", [])
    }
    parts = {
        i.id: {"name": i.name, "is_available": i.is_available, "allergens": i.allergens}
        for i in items
        if i.id in part_ids
    }
    return {"venue_id": venue.id, "at": at.isoformat(), "categories": result, "combo_parts": parts}


async def load_rules(session: AsyncSession, venue_id: str) -> list[tax.Rule]:
    rows = (
        await session.scalars(select(TaxRule).where(TaxRule.venue_id == venue_id, TaxRule.is_active))
    ).all()
    return [
        tax.Rule(
            code=r.code,
            name=r.name,
            rate_bp=r.rate_bp,
            applies_to=r.applies_to,
            compound=r.compound,
            sequence=r.sequence,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
        )
        for r in rows
    ]


@dataclass
class CartLine:
    menu_item_id: str
    quantity: int
    modifier_ids: list[str] = field(default_factory=list)
    notes: str | None = None
    combo_choices: list[str] = field(default_factory=list)  # one menu item id per combo slot
    hold: bool = False  # staff only: keep in the kitchen until fired (course timing)
    source: str | None = None  # "upsell" when the guest added it from a suggestion


# Station of a combo's own line: nothing to cook there; its parts go to their stations.
COMBO_STATION = "none"


@dataclass
class PricedLine:
    menu_item_id: str
    name: dict[str, Any]
    unit_price: int
    quantity: int
    modifiers: list[dict[str, Any]]
    notes: str | None
    allergens: list[str]
    line_total: int
    station: str
    tax_category: str
    parent: int | None = None  # index of the combo line this part belongs to
    hold: bool = False
    source: str | None = None


@dataclass(frozen=True)
class Discount:
    bp: int  # basis points: 1000 = 10%
    label: str  # shown on the bill, e.g. "Gold member 10%"


@dataclass
class Bill:
    gross: int  # sum of item lines before any discount
    discount_total: int
    totals: tax.Totals  # charges and taxes on the discounted amounts; totals.total is what is paid


def bill_totals(
    lines: list[tuple[int, str]], rules: list[tax.Rule], at: datetime, discount: Discount | None
) -> Bill:
    """Discount (loyalty tier) comes off each line first; service charge and taxes are then charged
    on what the guest actually pays for."""
    gross = sum(amount for amount, _ in lines)
    bp = discount.bp if discount else 0
    net = [tax.Line(amount - (amount * bp + 5_000) // 10_000, cat) for amount, cat in lines]
    totals = tax.calculate(net, rules, at)
    return Bill(gross, gross - totals.subtotal, totals)


@dataclass
class PricedCart:
    lines: list[PricedLine]
    totals: tax.Totals
    gross: int = 0
    discount_total: int = 0
    discount_label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lines": [line.__dict__ for line in self.lines],
            "subtotal": self.gross,
            "discount_total": self.discount_total,
            "discount_label": self.discount_label,
            "tax_lines": [t.__dict__ for t in self.totals.tax_lines],
            "tax_total": self.totals.tax_total,
            "total": self.totals.total,
        }


def _combo_parts(
    item: MenuItem, line: CartLine, items: dict[str, MenuItem], label: str
) -> list[tuple[MenuItem, int]]:
    """Check the guest's choice for every combo slot. Returns (part, upcharge) per slot."""
    slots = item.combo_slots or []
    if not slots:
        if line.combo_choices:
            raise AppError("not_a_combo", f"{label} is not a combo")
        return []
    if len(line.combo_choices) != len(slots):
        raise AppError("bad_combo", f"{label}: choose one item for each of the {len(slots)} parts")
    parts = []
    for slot, choice in zip(slots, line.combo_choices, strict=True):
        slot_name = slot.get("name", {}).get("en", "part")
        if choice not in slot.get("item_ids", []):
            raise AppError("bad_combo", f"{label}: that choice is not offered for {slot_name}")
        part = items.get(choice)
        if part is None or not part.is_active:
            raise AppError("bad_combo", f"{label}: {slot_name} option is no longer on the menu")
        if not part.is_available:
            raise AppError("item_unavailable", f"{part.name.get('en', part.id)} is sold out")
        parts.append((part, int(slot.get("upcharges", {}).get(choice, 0))))
    return parts


async def price_cart(
    session: AsyncSession, venue: Venue, cart: list[CartLine], at: datetime, discount: Discount | None = None
) -> PricedCart:
    """Price a cart from the database. Client-supplied prices are never trusted."""
    if not cart:
        raise AppError("empty_cart", "The order has no items")
    now = local_now(venue, at)
    ids = {c.menu_item_id for c in cart} | {i for c in cart for i in c.combo_choices}
    items = {
        i.id: i
        for i in (
            await session.scalars(select(MenuItem).where(MenuItem.venue_id == venue.id, MenuItem.id.in_(ids)))
        ).all()
    }
    cat_ids = {i.category_id for i in items.values()}
    cats = {
        c.id: c
        for c in (await session.scalars(select(MenuCategory).where(MenuCategory.id.in_(cat_ids)))).all()
    }

    offers = await active_offers(session, venue, at)
    lines: list[PricedLine] = []
    for c in cart:
        item = items.get(c.menu_item_id)
        cat = cats.get(item.category_id) if item else None
        if item is None or not item.is_active or cat is None or not cat.is_active:
            raise AppError("item_not_found", f"Menu item {c.menu_item_id} is not on the menu")
        label = item.name.get("en", item.id)
        if not item.is_available:
            raise AppError("item_unavailable", f"{label} is sold out")
        if not (in_windows(cat.windows, now) and in_windows(item.windows, now)):
            raise AppError("item_not_served_now", f"{label} is not served at this time")
        if not 1 <= c.quantity <= 99:
            raise AppError("bad_quantity", "Quantity must be between 1 and 99")
        if len(set(c.modifier_ids)) != len(c.modifier_ids):
            raise AppError("duplicate_modifier", "A modifier was selected twice")

        chosen: list[dict[str, Any]] = []
        remaining = set(c.modifier_ids)
        for group in item.modifier_groups:
            picked = [m for m in group.modifiers if m.id in remaining and m.is_active]
            remaining -= {m.id for m in picked}
            if not group.min_select <= len(picked) <= group.max_select:
                raise AppError(
                    "bad_modifiers",
                    f"{label}: choose {group.min_select}-{group.max_select} "
                    f"of {group.name.get('en', 'options')}",
                )
            chosen += [
                {"id": m.id, "group_id": group.id, "name": m.name, "price_delta": m.price_delta}
                for m in picked
            ]
        if remaining:
            raise AppError("bad_modifiers", f"{label}: unknown modifier")

        parts = _combo_parts(item, c, items, label)
        base = offer_price(item.price, offers[item.id].discount_bp) if item.id in offers else item.price
        unit = base + sum(m["price_delta"] for m in chosen) + sum(up for _, up in parts)
        if unit < 0:
            raise AppError("bad_modifiers", f"{label}: price below zero")
        parent = len(lines)
        lines.append(
            PricedLine(
                menu_item_id=item.id,
                name=item.name,
                unit_price=unit,
                quantity=c.quantity,
                modifiers=chosen,
                notes=(c.notes or None),
                allergens=sorted({*item.allergens, *(a for p, _ in parts for a in p.allergens)}),
                line_total=unit * c.quantity,
                station=COMBO_STATION if parts else item.station,
                tax_category=item.tax_category,
                hold=c.hold,
                source=c.source,
            )
        )
        for part, _ in parts:
            # The combo line carries the price and tax; parts are free lines for the kitchen.
            lines.append(
                PricedLine(
                    menu_item_id=part.id,
                    name=part.name,
                    unit_price=0,
                    quantity=c.quantity,
                    modifiers=[],
                    notes=None,
                    allergens=list(part.allergens),
                    line_total=0,
                    station=part.station,
                    tax_category=item.tax_category,
                    parent=parent,
                    hold=c.hold,
                )
            )

    from kiosk.services import inventory  # stock limits (R-INV); imported here to avoid a cycle

    await inventory.check_cart(session, venue.id, lines)
    rules = await load_rules(session, venue.id)
    bill = bill_totals([(ln.line_total, ln.tax_category) for ln in lines], rules, at, discount)
    label = discount.label if discount and bill.discount_total else None
    return PricedCart(lines, bill.totals, bill.gross, bill.discount_total, label)
