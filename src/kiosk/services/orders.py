"""Order engine. Services flush but never commit: the caller (router or job) commits."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from kiosk.domain.orders import (
    PRIORITY_RANK,
    REMAKE_REASONS,
    ItemStatus,
    PaymentStatus,
    Status,
    TransitionError,
    all_items_done,
    can_complete,
    check_transition,
    estimate_minutes,
    format_token,
    should_release_on_place,
)
from kiosk.errors import AppError, Conflict, NotFound
from kiosk.infra.models import MenuItem, Order, OrderEvent, OrderItem, Venue, utcnow
from kiosk.services import hybrid, inventory, posbridge, printing, sms, tables
from kiosk.services.counters import next_value
from kiosk.services.menu import (
    COMBO_STATION,
    CartLine,
    Discount,
    PricedCart,
    bill_totals,
    load_rules,
    local_now,
    price_cart,
)
from kiosk.services.serializers import order_dict
from kiosk.services.uow import Actor, UnitOfWork


def _transition(order: Order, target: Status) -> None:
    try:
        check_transition(order.status, target)
    except TransitionError as exc:
        raise Conflict("bad_transition", str(exc)) from exc
    order.status = target


async def changed(uow: UnitOfWork, order: Order, event: str, actor: Actor, **data: Any) -> dict[str, Any]:
    """Record an order change: event log, version bump, outbox snapshot, real-time event."""
    order.version += 1
    uow.session.add(
        OrderEvent(
            order_id=order.id,
            venue_id=order.venue_id,
            type=event,
            data=data,
            device_id=actor.device_id,
            staff_id=actor.staff_id,
        )
    )
    await uow.session.flush()
    snapshot = order_dict(order)
    # _event lets the other side (hub or cloud) tell its screens exactly what happened.
    # The guest's number travels only hub <-> cloud (never to screens), for texts in backup mode.
    uow.outbox(
        order.venue_id, "order.snapshot", {**snapshot, "_event": event, "notify_phone": order.notify_phone}
    )
    stations = sorted({i.station for i in order.items})
    topics = ["orders", "status", "kds", *(f"kds:{s}" for s in stations)]
    uow.emit(order.venue_id, event, {"order": snapshot, **data}, topics)
    await posbridge.on_event(uow, order, event)  # the restaurant's own POS, if connected
    return snapshot


async def get_order(uow: UnitOfWork, venue_id: str, order_id: str, lock: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id, Order.venue_id == venue_id)
    if lock:
        stmt = stmt.with_for_update()
    order = await uow.session.scalar(stmt)
    if order is None:
        raise NotFound("Order")
    return order


def _new_items(priced: PricedCart, offset: int = 0) -> list[OrderItem]:
    return [
        OrderItem(
            position=offset + pos,
            menu_item_id=ln.menu_item_id,
            name=ln.name,
            unit_price=ln.unit_price,
            quantity=ln.quantity,
            modifiers=ln.modifiers,
            notes=ln.notes,
            allergens=ln.allergens,
            line_total=ln.line_total,
            station=ln.station,
            tax_category=ln.tax_category,
            # A combo's own line has nothing to cook; its parts are cooked at their stations.
            kds_status=ItemStatus.DONE
            if ln.station == COMBO_STATION
            else ItemStatus.HELD
            if ln.hold
            else ItemStatus.QUEUED,
            parent_position=None if ln.parent is None else offset + ln.parent,
            source=ln.source,
        )
        for pos, ln in enumerate(priced.lines)
    ]


def _apply_cart(order: Order, priced: PricedCart) -> None:
    order.items = _new_items(priced)
    order.subtotal = priced.gross
    order.discount_total = priced.discount_total
    order.discount_label = priced.discount_label
    order.tax_lines = [t.__dict__ for t in priced.totals.tax_lines]
    order.tax_total = priced.totals.tax_total
    order.total = priced.totals.total


async def reprice(uow: UnitOfWork, venue: Venue, order: Order) -> None:
    """Recalculate the bill from the order's own lines (new round, member discount added)."""
    rules = await load_rules(uow.session, venue.id)
    lines = [(i.line_total, i.tax_category) for i in order.items if i.kds_status != ItemStatus.VOIDED]
    discount = Discount(order.discount_bp, order.discount_label or "") if order.discount_bp else None
    bill = bill_totals(lines, rules, utcnow(), discount)
    order.subtotal, order.discount_total = bill.gross, bill.discount_total
    order.tax_lines = [t.__dict__ for t in bill.totals.tax_lines]
    order.tax_total, order.total = bill.totals.tax_total, bill.totals.total


async def create_order(
    uow: UnitOfWork,
    venue: Venue,
    actor: Actor,
    channel: str,
    cart: list[CartLine],
    table_ref: str | None = None,
    notes: str | None = None,
    member: tuple[str, Discount | None] | None = None,
) -> Order:
    tab_mode = channel == "table" and bool(table_ref) and venue.setting("dine_in_mode") == "tab"
    if table_ref:
        await tables.ensure_can_order(uow, venue, table_ref, actor)  # closed tables don't take orders
        await tables.start_visit(uow, venue, table_ref)
    if tab_mode and table_ref:
        tab = await open_tab(uow, venue.id, table_ref)
        if tab is not None:
            return await add_round(uow, venue, tab, actor, cart)
    elif channel == "table" and table_ref and actor.staff_id is None:
        await _ensure_table_free(uow, venue.id, table_ref)
    if actor.staff_id is None and any(c.hold for c in cart):
        raise AppError("hold_staff_only", "Only staff can hold items for later")
    now = utcnow()
    discount = member[1] if member else None
    priced = await price_cart(uow.session, venue, cart, now, discount)
    business_date = local_now(venue, now).date().isoformat()
    number = await next_value(uow.session, venue.id, f"token:{business_date}")
    if hybrid.cloud_backup(venue):
        number += hybrid.BACKUP_TOKEN_OFFSET  # the cloud standing in for the hub: A501, K502...
    prefix = venue.setting("token_prefixes").get(channel, "A")
    # A tab cooks at once (like rule B): nobody can take food away unpaid, it is paid at the end.
    rule = "B" if tab_mode else venue.setting("release_rule")

    order = Order(
        venue_id=venue.id,
        token=format_token(prefix, number),
        business_date=business_date,
        channel=channel,
        table_ref=table_ref,
        status=Status.PLACED,
        payment_status=PaymentStatus.UNPAID,
        release_rule=rule,
        notes=notes,
        device_id=actor.device_id,
        placed_by_staff_id=actor.staff_id,
        is_tab=tab_mode,
        customer_id=member[0] if member else None,
        discount_bp=discount.bp if discount else 0,
        version=0,
        items=[],
        payments=[],
    )
    _apply_cart(order, priced)
    if not should_release_on_place(rule):
        order.expires_at = now + timedelta(minutes=int(venue.setting("unpaid_expiry_minutes")))
    uow.session.add(order)
    await uow.session.flush()
    await changed(uow, order, "order.created", actor)
    if should_release_on_place(rule):
        await release(uow, venue, order, actor)
    return order


async def open_tab(uow: UnitOfWork, venue_id: str, table_ref: str) -> Order | None:
    order: Order | None = await uow.session.scalar(
        select(Order)
        .where(
            Order.venue_id == venue_id,
            Order.table_ref == table_ref,
            Order.is_tab,
            Order.status.in_([Status.PLACED, Status.IN_KITCHEN, Status.READY]),
            Order.payment_status.in_([PaymentStatus.UNPAID, PaymentStatus.PENDING]),
        )
        .order_by(Order.created_at.desc())
    )
    return order


async def add_round(uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, cart: list[CartLine]) -> Order:
    """Another round on an open tab: new items go to the kitchen, the bill grows."""
    if order.payment_status == PaymentStatus.PENDING:
        raise Conflict("bill_being_paid", "The bill is being paid. Order again after payment")
    if actor.staff_id is None and any(c.hold for c in cart):
        raise AppError("hold_staff_only", "Only staff can hold items for later")
    now = utcnow()
    priced = await price_cart(uow.session, venue, cart, now)
    new = _new_items(priced, offset=len(order.items))
    order.items.extend(new)
    await reprice(uow, venue, order)
    order.served_at = None
    if order.status == Status.READY:
        _transition(order, Status.IN_KITCHEN)
        order.ready_at = None
    order.promised_at = now + timedelta(minutes=await _estimate(uow, venue, order))
    if order.status != Status.PLACED:  # already released: the new round goes straight to cooking
        await inventory.consume(uow, venue, order, new, actor)
    await changed(uow, order, "order.round_added", actor, items=[i.name.get("en") for i in new])
    return order


async def mark_served(uow: UnitOfWork, order: Order, actor: Actor) -> Order:
    """A waiter took the ready food to the table. Paid orders are finished; a tab stays open."""
    if order.status != Status.READY:
        raise Conflict("not_ready", "Only ready orders can be served")
    order.served_at = utcnow()
    if can_complete(order.payment_status):
        _transition(order, Status.COMPLETED)
        order.completed_at = order.served_at
    await changed(uow, order, "order.served", actor)
    return order


async def _ensure_table_free(uow: UnitOfWork, venue_id: str, table_ref: str) -> None:
    """A table with an unpaid order waiting for payment is locked for guests until it is paid,
    cancelled or expires, so nobody can keep ordering without paying. Staff can still order."""
    waiting = await uow.session.scalar(
        select(Order.token).where(
            Order.venue_id == venue_id,
            Order.table_ref == table_ref,
            Order.channel == "table",
            Order.status == Status.PLACED,
            Order.payment_status.in_([PaymentStatus.UNPAID, PaymentStatus.PENDING]),
        )
    )
    if waiting:
        raise Conflict("table_locked", f"Order {waiting} is waiting for payment. Please pay it first")


async def replace_items(
    uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, cart: list[CartLine]
) -> Order:
    """Edit freely before the kitchen starts and before any payment is in progress."""
    if order.status != Status.PLACED or order.payment_status != PaymentStatus.UNPAID:
        raise Conflict(
            "order_locked", "Items can only be changed before the kitchen starts and before payment"
        )
    before = [(i.menu_item_id, i.quantity) for i in order.items]
    priced = await price_cart(uow.session, venue, cart, utcnow())
    _apply_cart(order, priced)
    await changed(uow, order, "order.items_replaced", actor, before=before)
    return order


async def release(uow: UnitOfWork, venue: Venue, order: Order, actor: Actor) -> None:
    """Send the order to the kitchen."""
    _transition(order, Status.IN_KITCHEN)
    order.released_at = utcnow()
    order.expires_at = None
    order.promised_at = order.released_at + timedelta(minutes=await _estimate(uow, venue, order))
    await inventory.consume(uow, venue, order, list(order.items), actor)
    await changed(uow, order, "order.released", actor)
    if venue.setting("print_kitchen_backup"):
        await printing.enqueue(
            uow, venue, "kitchen", printing.render_kitchen_ticket(order), f"kitchen-{order.token}", order
        )


async def _estimate(uow: UnitOfWork, venue: Venue, order: Order) -> int:
    ids = {i.menu_item_id for i in order.items if i.station != COMBO_STATION}
    preps = (
        await uow.session.execute(select(MenuItem.id, MenuItem.prep_minutes).where(MenuItem.id.in_(ids)))
    ).all()
    default = int(venue.setting("default_prep_minutes"))
    open_before = await uow.session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.venue_id == venue.id, Order.status == Status.IN_KITCHEN, Order.id != order.id)
    )
    return estimate_minutes(
        [p or default for _, p in preps] or [default],
        int(open_before or 0),
        int(venue.setting("kitchen_cooks")),
    )


async def set_priority(uow: UnitOfWork, order: Order, actor: Actor, priority: str) -> Order:
    if priority not in PRIORITY_RANK:
        raise AppError("bad_priority", f"Priority must be one of {', '.join(PRIORITY_RANK)}")
    if order.status in (Status.COMPLETED, Status.CANCELLED, Status.EXPIRED, Status.VOIDED):
        raise Conflict("order_closed", f"Order is {order.status}")
    before = order.priority
    order.priority = priority
    await changed(uow, order, "order.priority", actor, before=before, priority=priority)
    return order


async def fire(uow: UnitOfWork, order: Order, actor: Actor, item_ids: list[str] | None) -> Order:
    """Send held items to the kitchen now (next course)."""
    fired = []
    for item in order.items:
        if item.kds_status == ItemStatus.HELD and (not item_ids or item.id in item_ids):
            item.kds_status = ItemStatus.QUEUED
            fired.append(item.id)
    if not fired:
        raise Conflict("nothing_held", "No held items to fire")
    await changed(uow, order, "kds.fired", actor, item_ids=fired)
    return order


async def remake(uow: UnitOfWork, order: Order, item_id: str, actor: Actor, reason: str) -> Order:
    """Cook an item again (burnt, dropped, wrong...). The reason is kept for the owner's reports."""
    if reason not in REMAKE_REASONS:
        raise AppError("bad_reason", f"Reason must be one of {', '.join(REMAKE_REASONS)}")
    _require_kitchen(order)
    item = _find_item(order, item_id)
    if item.kds_status != ItemStatus.DONE or item.station == COMBO_STATION:
        raise Conflict("bad_item_state", "Only finished items can be remade")
    item.kds_status = ItemStatus.QUEUED
    item.done_at = None
    item.started_at = None
    item.remake_count += 1
    if order.status == Status.READY:
        _transition(order, Status.IN_KITCHEN)
        order.ready_at = None
    await changed(uow, order, "kds.remake", actor, item_id=item.id, station=item.station, reason=reason)
    return order


async def cancel(uow: UnitOfWork, order: Order, actor: Actor, reason: str) -> Order:
    if order.payment_status == PaymentStatus.PAID:
        raise Conflict("order_paid", "A paid order must be voided with a refund, not cancelled")
    _transition(order, Status.CANCELLED)
    _cancel_pending_payments(order)
    order.payment_status = PaymentStatus.UNPAID
    await changed(uow, order, "order.cancelled", actor, reason=reason)
    return order


def _cancel_pending_payments(order: Order) -> None:
    for p in order.payments:
        if p.status == "pending":
            p.status = "cancelled"
            p.completed_at = utcnow()


async def expire_due(uow: UnitOfWork, now: datetime | None = None) -> list[Order]:
    """Cancel "Pay at cashier" orders that were never paid (release rule A).

    On the cloud, venues whose hub is in charge are skipped: the hub expires its own orders."""
    now = now or utcnow()
    due = list(
        (
            await uow.session.scalars(
                select(Order).where(
                    Order.status == Status.PLACED,
                    Order.payment_status.in_([PaymentStatus.UNPAID, PaymentStatus.PENDING]),
                    Order.expires_at.is_not(None),
                    Order.expires_at <= now,
                )
            )
        ).all()
    )
    run_by_hub: dict[str, bool] = {}
    for order in list(due):
        if order.venue_id not in run_by_hub:
            venue = await uow.session.get(Venue, order.venue_id)
            run_by_hub[order.venue_id] = venue is not None and await hybrid.hub_in_charge(uow, venue)
        if run_by_hub[order.venue_id]:
            due.remove(order)
    for order in due:
        order.status = Status.EXPIRED
        order.payment_status = PaymentStatus.UNPAID
        _cancel_pending_payments(order)
        await changed(uow, order, "order.expired", Actor(venue_id=order.venue_id))
    return list(due)


# ---------------------------------------------------------------- kitchen


def _mark_ready_if_done(order: Order) -> bool:
    if order.status == Status.IN_KITCHEN and all_items_done([i.kds_status for i in order.items]):
        order.status = Status.READY
        order.ready_at = utcnow()
        return True
    return False


def _find_item(order: Order, item_id: str) -> OrderItem:
    for item in order.items:
        if item.id == item_id:
            return item
    raise NotFound("Order item")


def _require_kitchen(order: Order) -> None:
    if order.status not in (Status.IN_KITCHEN, Status.READY):
        raise Conflict("not_in_kitchen", "This order is not in the kitchen")


async def item_start(uow: UnitOfWork, order: Order, item_id: str, actor: Actor) -> Order:
    _require_kitchen(order)
    item = _find_item(order, item_id)
    if item.kds_status != ItemStatus.QUEUED:
        raise Conflict("bad_item_state", f"Item is {item.kds_status}")
    item.kds_status = ItemStatus.IN_PROGRESS
    item.started_at = utcnow()
    await changed(uow, order, "kds.item_started", actor, item_id=item.id, station=item.station)
    return order


async def item_done(uow: UnitOfWork, order: Order, item_id: str, actor: Actor) -> Order:
    _require_kitchen(order)
    item = _find_item(order, item_id)
    if item.kds_status not in (ItemStatus.QUEUED, ItemStatus.IN_PROGRESS):
        raise Conflict("bad_item_state", f"Item is {item.kds_status}")
    item.kds_status = ItemStatus.DONE
    item.done_at = utcnow()
    became_ready = _mark_ready_if_done(order)
    await changed(uow, order, "kds.item_done", actor, item_id=item.id, station=item.station)
    if became_ready:
        await changed(uow, order, "order.ready", actor)
        await _text_guest(uow, order)
    return order


async def bump(uow: UnitOfWork, order: Order, station: str | None, actor: Actor) -> Order:
    """Mark every item of this station (or all stations) done."""
    _require_kitchen(order)
    now = utcnow()
    bumped = []
    for item in order.items:
        if item.kds_status in (ItemStatus.QUEUED, ItemStatus.IN_PROGRESS) and (
            station is None or item.station == station
        ):
            item.kds_status = ItemStatus.DONE
            item.started_at = item.started_at or order.released_at
            item.done_at = now
            bumped.append(item.id)
    if not bumped:
        raise Conflict("nothing_to_bump", "No open items for this station")
    became_ready = _mark_ready_if_done(order)
    await changed(uow, order, "kds.bumped", actor, station=station, item_ids=bumped)
    if became_ready:
        await changed(uow, order, "order.ready", actor)
        await _text_guest(uow, order)
    return order


async def recall(uow: UnitOfWork, venue_id: str, station: str | None, actor: Actor) -> Order:
    """Bring back the most recently bumped ticket for a station."""
    stmt = (
        select(OrderEvent)
        .where(OrderEvent.venue_id == venue_id, OrderEvent.type == "kds.bumped")
        .order_by(OrderEvent.created_at.desc())
        .limit(50)
    )
    for ev in (await uow.session.scalars(stmt)).all():
        if ev.data.get("station") != station:
            continue
        order = await get_order(uow, venue_id, ev.order_id)
        if order.status not in (Status.IN_KITCHEN, Status.READY):
            continue
        ids = set(ev.data.get("item_ids", []))
        reopened = False
        for item in order.items:
            if item.id in ids and item.kds_status == ItemStatus.DONE:
                item.kds_status = ItemStatus.IN_PROGRESS
                item.done_at = None
                reopened = True
        if not reopened:
            continue
        if order.status == Status.READY:
            _transition(order, Status.IN_KITCHEN)
            order.ready_at = None
        await changed(uow, order, "kds.recalled", actor, station=station, item_ids=sorted(ids))
        return order
    raise NotFound("Recently bumped ticket")


async def complete(uow: UnitOfWork, order: Order, actor: Actor) -> Order:
    """Food handed over to the guest."""
    if not can_complete(order.payment_status):
        raise Conflict("unpaid", "This order is not paid yet. Take payment before handing over")
    _transition(order, Status.COMPLETED)
    order.completed_at = utcnow()
    await changed(uow, order, "order.completed", actor)
    return order


async def void(uow: UnitOfWork, order: Order, actor: Actor, reason: str) -> Order:
    """Stop an order that is already in the kitchen. Paid money is refunded by the caller."""
    was_in_kitchen = order.status in (Status.IN_KITCHEN, Status.READY)
    _transition(order, Status.VOIDED)
    uncooked = [i for i in order.items if i.kds_status in (ItemStatus.QUEUED, ItemStatus.HELD)]
    if was_in_kitchen and uncooked:
        venue = await uow.session.get(Venue, order.venue_id)
        if venue is not None:
            await inventory.give_back(uow, venue, order, uncooked, actor)
    for item in order.items:
        if item.kds_status != ItemStatus.DONE:
            item.kds_status = ItemStatus.VOIDED
    _cancel_pending_payments(order)
    if order.payment_status == PaymentStatus.PENDING:
        order.payment_status = PaymentStatus.UNPAID
    await changed(uow, order, "order.voided", actor, reason=reason)
    uow.audit(actor, "order.void", order.id, reason=reason, total=order.total)
    return order


async def _text_guest(uow: UnitOfWork, order: Order) -> None:
    venue = await uow.session.get(Venue, order.venue_id)
    if venue is not None:
        await sms.queue(uow, venue, order, "ready")


def ensure_open(order: Order) -> None:
    if order.status in (Status.CANCELLED, Status.EXPIRED, Status.VOIDED):
        raise AppError("order_closed", f"Order is {order.status}", 409)
