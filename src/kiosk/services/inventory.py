"""Inventory and auto stock-out (R-INV).

Stock is counted in portions per menu item. Only items the venue chose to track have a StockItem;
everything else is unlimited, as before.

  - Sold portions come off when the order goes to the kitchen (release, or a new round on a tab).
  - A void gives back the portions the kitchen had not started.
  - At zero the item is sold out on every screen (the "86"), and comes back by itself when a
    delivery or a count puts stock back. Staff can still switch it by hand.
  - At or below the "low" level the kitchen, cashier and owner get a low-stock alert.
  - Guests cannot order more than is left.
Every change is a StockMove, so the owner can see where stock went (sales, waste, deliveries).
"""

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.domain.orders import ItemStatus
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import MenuItem, Order, OrderItem, StockItem, StockMove, Venue, new_id, utcnow
from kiosk.services.menu import COMBO_STATION, PricedLine
from kiosk.services.uow import Actor, UnitOfWork

MOVE_KINDS = ("delivery", "count", "waste")


def _portions(items: list[OrderItem] | list[PricedLine]) -> Counter[str]:
    """Portions per menu item. A combo line is only a price: its parts are what gets cooked."""
    need: Counter[str] = Counter()
    for i in items:
        if i.station != COMBO_STATION:
            need[i.menu_item_id] += i.quantity
    return need


async def stock_for(session: AsyncSession, venue_id: str, ids: set[str]) -> dict[str, StockItem]:
    if not ids:
        return {}
    rows = await session.scalars(
        select(StockItem).where(StockItem.venue_id == venue_id, StockItem.menu_item_id.in_(ids))
    )
    return {s.menu_item_id: s for s in rows.all()}


async def check_cart(session: AsyncSession, venue_id: str, lines: list[PricedLine]) -> None:
    need = _portions(lines)
    stock = await stock_for(session, venue_id, set(need))
    for item_id, qty in need.items():
        s = stock.get(item_id)
        if s is not None and qty > max(s.on_hand, 0):
            name = next(ln.name.get("en", item_id) for ln in lines if ln.menu_item_id == item_id)
            raise AppError(
                "not_enough_stock",
                f"Only {max(s.on_hand, 0)} {name} left" if s.on_hand > 0 else f"{name} is sold out",
            )


async def _move(
    uow: UnitOfWork,
    venue: Venue,
    stock: StockItem,
    change: int,
    reason: str,
    actor: Actor,
    order_id: str | None = None,
) -> None:
    before = stock.on_hand
    stock.on_hand += change
    move = StockMove(
        id=new_id(),
        venue_id=venue.id,
        menu_item_id=stock.menu_item_id,
        change=change,
        reason=reason,
        order_id=order_id,
        by=actor.staff_id or actor.admin_id or actor.device_id or "system",
        created_at=utcnow(),
    )
    uow.session.add(move)
    # The other side (cloud or the restaurant's hub) applies the same move once.
    uow.outbox(
        venue.id,
        "stock.move",
        {
            "id": move.id,
            "menu_item_id": move.menu_item_id,
            "change": change,
            "reason": reason,
            "order_id": order_id,
            "by": move.by,
            "created_at": move.created_at.isoformat(),
        },
    )
    await _after_change(uow, venue, stock, before)


async def _after_change(uow: UnitOfWork, venue: Venue, stock: StockItem, before: int) -> None:
    item = await uow.session.get(MenuItem, stock.menu_item_id)
    if item is None:
        return
    switched = None
    if stock.on_hand <= 0 and stock.auto_86 and item.is_available:
        item.is_available, stock.auto_off, switched = False, True, False
    elif stock.on_hand > 0 and stock.auto_off:
        stock.auto_off = False
        if not item.is_available:
            item.is_available, switched = True, True
    if switched is not None:
        item.availability_changed_at = utcnow()
        uow.emit(
            venue.id,
            "menu.item_availability",
            {"item_id": item.id, "is_available": switched, "name": item.name, "by": "stock"},
            ["menu", "orders", "kds"],
        )
        uow.outbox(venue.id, "menu.availability", {"item_id": item.id, "is_available": switched})
    if 0 < stock.on_hand <= stock.low_at < before:
        uow.emit(
            venue.id,
            "stock.low",
            {"item_id": item.id, "name": item.name, "on_hand": stock.on_hand},
            ["orders", "kds"],
        )


async def consume(uow: UnitOfWork, venue: Venue, order: Order, items: list[OrderItem], actor: Actor) -> None:
    """Take sold portions off stock when they go to the kitchen."""
    need = _portions([i for i in items if i.kds_status != ItemStatus.VOIDED])
    stock = await stock_for(uow.session, venue.id, set(need))
    for item_id, qty in need.items():
        if item_id in stock:
            await _move(uow, venue, stock[item_id], -qty, "sale", actor, order.id)


async def give_back(
    uow: UnitOfWork, venue: Venue, order: Order, items: list[OrderItem], actor: Actor
) -> None:
    """A void returns the portions that were not cooked yet."""
    need = _portions(items)
    stock = await stock_for(uow.session, venue.id, set(need))
    for item_id, qty in need.items():
        if item_id in stock:
            await _move(uow, venue, stock[item_id], qty, "void_return", actor, order.id)


async def track(
    uow: UnitOfWork,
    venue: Venue,
    menu_item_id: str,
    actor: Actor,
    *,
    on_hand: int | None = None,
    low_at: int | None = None,
    auto_86: bool | None = None,
    perishable_until: datetime | None = None,
    clear_perishable: bool = False,
) -> StockItem:
    """Start tracking an item, or change its settings. Setting on_hand counts as a stock count."""
    item = await uow.session.get(MenuItem, menu_item_id)
    if item is None or item.venue_id != venue.id:
        raise NotFound("Menu item")
    if item.combo_slots:
        raise AppError("combo_not_tracked", "Track the items inside a combo, not the combo")
    stock = (await stock_for(uow.session, venue.id, {menu_item_id})).get(menu_item_id)
    if stock is None:
        stock = StockItem(venue_id=venue.id, menu_item_id=menu_item_id, on_hand=0, low_at=5, auto_86=True)
        uow.session.add(stock)
    if low_at is not None:
        stock.low_at = max(0, low_at)
    if auto_86 is not None:
        stock.auto_86 = auto_86
    if perishable_until is not None or clear_perishable:
        stock.perishable_until = perishable_until
    if on_hand is not None:
        await adjust(uow, venue, stock, "count", on_hand, actor)
    uow.audit(actor, "stock.track", menu_item_id, on_hand=stock.on_hand, low_at=stock.low_at)
    return stock


async def adjust(uow: UnitOfWork, venue: Venue, stock: StockItem, kind: str, qty: int, actor: Actor) -> None:
    """delivery: +qty, waste: -qty, count: the shelf has exactly qty."""
    if kind not in MOVE_KINDS:
        raise AppError("bad_stock_move", f"Kind must be one of {', '.join(MOVE_KINDS)}")
    if qty < 0 or (kind != "count" and qty == 0):
        raise AppError("bad_quantity", "Quantity must be a positive number")
    change = {"delivery": qty, "waste": -qty, "count": qty - stock.on_hand}[kind]
    if kind == "waste" and qty > max(stock.on_hand, 0):
        raise AppError("bad_quantity", f"Only {stock.on_hand} in stock")
    await _move(uow, venue, stock, change, kind, actor)
    uow.audit(actor, f"stock.{kind}", stock.menu_item_id, change=change, on_hand=stock.on_hand)


async def get(uow: UnitOfWork, venue: Venue, menu_item_id: str) -> StockItem:
    stock = (await stock_for(uow.session, venue.id, {menu_item_id})).get(menu_item_id)
    if stock is None:
        raise NotFound("Stock for this item")
    return stock


def stock_dict(s: StockItem, item: MenuItem | None) -> dict[str, Any]:
    return {
        "menu_item_id": s.menu_item_id,
        "name": item.name if item else None,
        "on_hand": s.on_hand,
        "low_at": s.low_at,
        "auto_86": s.auto_86,
        "state": "out" if s.on_hand <= 0 else "low" if s.on_hand <= s.low_at else "ok",
        "is_available": item.is_available if item else None,
        "perishable_until": s.perishable_until.isoformat() if s.perishable_until else None,
    }


async def overview(uow: UnitOfWork, venue: Venue) -> dict[str, Any]:
    rows = (await uow.session.scalars(select(StockItem).where(StockItem.venue_id == venue.id))).all()
    items = {
        m.id: m
        for m in (
            await uow.session.scalars(select(MenuItem).where(MenuItem.id.in_([s.menu_item_id for s in rows])))
        ).all()
    }
    stock = sorted(
        (stock_dict(s, items.get(s.menu_item_id)) for s in rows),
        key=lambda d: ({"out": 0, "low": 1, "ok": 2}[d["state"]], (d["name"] or {}).get("en", "")),
    )
    moves = (
        await uow.session.scalars(
            select(StockMove)
            .where(StockMove.venue_id == venue.id)
            .order_by(StockMove.created_at.desc())
            .limit(50)
        )
    ).all()
    wasted: Counter[str] = Counter()
    for m in moves:
        if m.reason == "waste":
            wasted[m.menu_item_id] += -m.change
    return {
        "items": stock,
        "moves": [
            {
                "menu_item_id": m.menu_item_id,
                "name": items[m.menu_item_id].name if m.menu_item_id in items else None,
                "change": m.change,
                "reason": m.reason,
                "order_id": m.order_id,
                "by": m.by,
                "at": m.created_at.isoformat(),
            }
            for m in moves
        ],
        "low": [d for d in stock if d["state"] != "ok"],
        "waste_recent": dict(wasted),
    }
