from datetime import timedelta
from typing import Any

from sqlalchemy import select

from kiosk.domain.orders import PaymentStatus, Status, should_release_on_payment
from kiosk.errors import AppError, Conflict, NotFound
from kiosk.infra.gateway import get_gateway
from kiosk.infra.models import CashShift, Customer, Device, Invoice, Order, Payment, Venue, utcnow
from kiosk.infra.terminal import get_terminal
from kiosk.services import hybrid, loyalty, printing, sms, tables
from kiosk.services import orders as order_svc
from kiosk.services.counters import next_value
from kiosk.services.plans import require_module
from kiosk.services.serializers import order_dict
from kiosk.services.uow import Actor, UnitOfWork
from kiosk.sync.state import lankaqr_available


def remaining(order: Order) -> int:
    return order.total - order.paid_total


def _part(venue: Venue, order: Order, amount: int | None) -> int:
    """How much this payment covers: the rest of the bill, or one share of a split bill."""
    left = remaining(order)
    if amount is None or amount == left:
        return left
    if amount <= 0 or amount > left:
        raise AppError("bad_amount", f"Amount must be between 0.01 and what is left ({left / 100:.2f})")
    require_module(venue, "R-SPLIT")
    return amount


HOLD_SECONDS = 120


def _ensure_payable(order: Order, actor: Actor | None = None) -> None:
    if order.status in (Status.CANCELLED, Status.EXPIRED, Status.VOIDED):
        raise Conflict("order_closed", f"Order is {order.status}")
    if order.payment_status in (PaymentStatus.PAID, PaymentStatus.REFUNDED):
        raise Conflict("already_paid", "This order is already paid")
    held = order.pay_hold_until is not None and order.pay_hold_until > utcnow()
    # actor None: the system (a bank callback, the restaurant's own POS): the money already moved.
    if held and actor is not None and actor.staff_id != order.pay_hold_by:
        raise Conflict("being_paid", f"{order.pay_hold_name or 'Someone'} is taking this payment right now")


def hold_payment(order: Order, actor: Actor, staff_name: str) -> None:
    """Start taking a payment: the bill is yours for two minutes (others see who is taking it)."""
    _ensure_payable(order, actor)
    order.pay_hold_by, order.pay_hold_name = actor.staff_id, staff_name
    order.pay_hold_until = utcnow() + timedelta(seconds=HOLD_SECONDS)


def release_payment(order: Order, actor: Actor | None = None, force: bool = False) -> None:
    if force or actor is None or order.pay_hold_by in (None, actor.staff_id):
        order.pay_hold_by = order.pay_hold_name = order.pay_hold_until = None


async def open_shift_for(uow: UnitOfWork, venue_id: str, device_id: str | None) -> CashShift | None:
    if device_id is None:
        return None
    result: CashShift | None = await uow.session.scalar(
        select(CashShift).where(
            CashShift.venue_id == venue_id,
            CashShift.device_id == device_id,
            CashShift.closed_at.is_(None),
        )
    )
    return result


async def _issue_invoice(uow: UnitOfWork, venue: Venue, order: Order) -> Invoice:
    existing = await uow.session.scalar(select(Invoice).where(Invoice.order_id == order.id))
    if existing:
        return existing
    n = await next_value(uow.session, venue.id, "invoice")
    inv = Invoice(
        venue_id=venue.id,
        order_id=order.id,
        # Backup mode (cloud standing in for the hub) uses its own series, so numbers never clash.
        number=f"{venue.code}-C{n:07d}" if hybrid.cloud_backup(venue) else f"{venue.code}-{n:08d}",
        total=order.total,
        snapshot=order_dict(order),
    )
    uow.session.add(inv)
    await uow.session.flush()
    uow.outbox(
        venue.id,
        "invoice",
        {
            "id": inv.id,
            "order_id": order.id,
            "number": inv.number,
            "total": inv.total,
            "issued_at": inv.issued_at.isoformat(),
            "snapshot": inv.snapshot,
        },
    )
    return inv


async def _settle(
    uow: UnitOfWork, venue: Venue, order: Order, payment: Payment, actor: Actor, drawer: bool
) -> None:
    """A charge succeeded: update the order, issue the invoice, release to the kitchen."""
    payment.status = "succeeded"
    payment.completed_at = utcnow()
    order.paid_total += payment.amount
    if order.paid_total < order.total:
        order.payment_status = PaymentStatus.UNPAID
        await order_svc.changed(uow, order, "payment.partial", actor, payment_id=payment.id)
        return
    order.payment_status = PaymentStatus.PAID
    release_payment(order, force=True)
    if order.customer_id:
        member = await uow.session.get(Customer, order.customer_id)
        if member is not None and member.forgotten_at is None:
            loyalty.earn(venue, order, member)
    await uow.session.flush()
    invoice = await _issue_invoice(uow, venue, order)
    if order.payment_status == PaymentStatus.PAID:
        await sms.queue(uow, venue, order, "receipt")
    await order_svc.changed(uow, order, "order.paid", actor, payment_id=payment.id, invoice=invoice.number)
    if should_release_on_payment(order.status, order.release_rule):
        await order_svc.release(uow, venue, order, actor)
    elif order.is_tab and order.status == Status.READY and order.served_at:
        # The last round was already served at the table: paying the tab finishes it.
        await order_svc.complete(uow, order, actor)
    if order.table_ref and order.payment_status == PaymentStatus.PAID:
        await tables.bill_settled(uow, venue, order.table_ref)
    if order.is_tab and order.table_ref and order.payment_status == PaymentStatus.PAID:
        # The bill is paid: the visit is over, the table takes no new orders until staff open it.
        await tables.set_open(uow, venue, order.table_ref, False, actor)
        await tables.end_visit(uow, venue, order.table_ref)  # paid: clean it once the guests have gone
    await printing.enqueue(
        uow,
        venue,
        "receipt",
        printing.render_receipt(venue, order, invoice, drawer),
        f"receipt-{order.token}",
        source=payment.device_id or order.device_id,  # the kiosk or till where the guest paid
    )


METHOD_NAMES = {"cash": "Cash", "lankaqr": "QR payment", "card": "Card"}


def method_on(venue: Venue, method: str) -> bool:
    return bool(
        {**{"cash": True, "lankaqr": True, "card": True}, **venue.setting("payment_methods")}.get(method)
    )


def _ensure_method(venue: Venue, method: str) -> None:
    if not method_on(venue, method):
        raise AppError("payment_method_off", f"{METHOD_NAMES[method]} payments are switched off here")


async def pay_cash(
    uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, tendered: int, amount: int | None = None
) -> Payment:
    _ensure_payable(order, actor)
    _ensure_method(venue, "cash")
    if order.payment_status == PaymentStatus.PENDING:
        _cancel_pending(order)
    shift = await open_shift_for(uow, venue.id, actor.device_id)
    if shift is None and actor.device_id and actor.staff_id:
        device = await uow.session.get(Device, actor.device_id)
        if device is not None and device.type == "waiter":
            # A waiter collecting cash at the table: their own cash bag opens by itself (float 0);
            # they hand it over at the end of service (close the shift with what they bring).
            shift = CashShift(
                venue_id=venue.id, device_id=device.id, opened_by=actor.staff_id, opening_float=0
            )
            uow.session.add(shift)
            await uow.session.flush()
            from kiosk.services.shifts import shift_dict  # shifts imports this module

            uow.outbox(venue.id, "shift", shift_dict(shift))
    if shift is None:
        raise AppError("no_open_shift", "Open a cash shift on this device before taking cash")
    amount = _part(venue, order, amount)
    if tendered < amount:
        raise AppError("insufficient_cash", f"Tendered {tendered} is less than due {amount}")
    payment = Payment(
        venue_id=venue.id,
        method="cash",
        amount=amount,
        status="pending",
        tendered=tendered,
        change_given=tendered - amount,
        shift_id=shift.id,
        device_id=actor.device_id,
        staff_id=actor.staff_id,
    )
    order.payments.append(payment)
    await uow.session.flush()
    await _settle(uow, venue, order, payment, actor, drawer=True)
    return payment


async def pay_card(
    uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, external_ref: str, amount: int | None = None
) -> Payment:
    """Record a card payment approved on the bank's terminal (the terminal is not integrated)."""
    _ensure_payable(order, actor)
    _ensure_method(venue, "card")
    if order.payment_status == PaymentStatus.PENDING:
        _cancel_pending(order)
    shift = await open_shift_for(uow, venue.id, actor.device_id)
    payment = Payment(
        venue_id=venue.id,
        method="card",
        amount=_part(venue, order, amount),
        status="pending",
        external_ref=external_ref,
        shift_id=shift.id if shift else None,
        device_id=actor.device_id,
        staff_id=actor.staff_id,
    )
    order.payments.append(payment)
    await uow.session.flush()
    await _settle(uow, venue, order, payment, actor, drawer=False)
    return payment


async def pay_by_pos(
    uow: UnitOfWork, venue: Venue, order: Order, reference: str, how: str, amount: int | None = None
) -> Payment:
    """The guest paid at the restaurant's own POS (R-BRIDGE). The POS says so; we release to the
    kitchen, print, earn points. `how` is what the POS took (cash, card...), kept for reports."""
    _ensure_payable(order)
    if order.payment_status == PaymentStatus.PENDING:
        _cancel_pending(order)
    actor = Actor(venue_id=venue.id)
    payment = Payment(
        venue_id=venue.id,
        method="pos",
        amount=_part(venue, order, amount),
        status="pending",
        external_ref=f"{how[:20]}:{reference}"[:80],
    )
    order.payments.append(payment)
    await uow.session.flush()
    await _settle(uow, venue, order, payment, actor, drawer=False)
    return payment


def _cancel_pending(order: Order) -> None:
    for p in order.payments:
        if p.status == "pending":
            p.status = "cancelled"
            p.completed_at = utcnow()
    order.payment_status = PaymentStatus.UNPAID


async def start_lankaqr(
    uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, amount: int | None = None
) -> Payment:
    _ensure_payable(order, actor)
    _ensure_method(venue, "lankaqr")
    if not lankaqr_available():
        raise AppError(
            "lankaqr_unavailable",
            "QR payment is temporarily unavailable. Please pay at the counter",
            503,
        )
    amount = _part(venue, order, amount)
    for p in order.payments:
        if p.method == "lankaqr" and p.status == "pending" and p.amount == amount:
            return p  # re-show the same QR instead of creating a second one
    _cancel_pending(order)
    qr = await get_gateway().create_qr(order.id, amount, reference=order.token)
    shift = await open_shift_for(uow, venue.id, actor.device_id)
    payment = Payment(
        venue_id=venue.id,
        method="lankaqr",
        amount=amount,
        status="pending",
        gateway_ref=qr.gateway_ref,
        qr_payload=qr.qr_payload,
        shift_id=shift.id if shift else None,
        device_id=actor.device_id,
        staff_id=actor.staff_id,
    )
    order.payments.append(payment)
    order.payment_status = PaymentStatus.PENDING
    await uow.session.flush()
    await order_svc.changed(uow, order, "payment.qr_started", actor, payment_id=payment.id)
    return payment


# ---------------------------------------------------------------- card terminals (tap / chip)

CARD_MODES = ("reader", "softpos")
# Card networks certify SoftPOS (tap on the tablet itself) only where staff take the payment.
ATTENDED_DEVICES = ("cashier", "waiter")
# Table screens may use tap-on-tablet only while a waiter is logged in on them (waiter assist):
# card-scheme rules allow SoftPOS on staff-operated devices, never for a guest alone.
ASSISTED_DEVICES = ("table",)


def card_setup(device: Device) -> dict[str, Any] | None:
    card = (device.settings or {}).get("card") or {}
    return card if card.get("mode") in CARD_MODES else None


async def start_card(
    uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, device: Device, amount: int | None = None
) -> Payment:
    """Ask this screen's card terminal to charge what is left on the order.

    The guest taps or inserts a card on the terminal; the processor's signed callback then
    settles the payment (see handle_terminal_callback). Card numbers never reach us.
    """
    _ensure_payable(order, actor)
    _ensure_method(venue, "card")
    card = card_setup(device)
    if card is None:
        raise AppError(
            "no_card_terminal", "This screen has no card reader. Please pay by QR or at the cashier"
        )
    if card["mode"] == "softpos" and device.type not in ATTENDED_DEVICES:
        if device.type not in ASSISTED_DEVICES:
            raise AppError("softpos_attended_only", "Tap-on-tablet is only allowed on staff screens")
        if actor.staff_id is None:
            raise AppError(
                "softpos_needs_staff",
                "Tap on this tablet needs a waiter: tap Staff and enter a PIN first, or pay by QR",
            )
    amount = _part(venue, order, amount)
    for p in order.payments:
        if p.method == "card" and p.status == "pending" and p.gateway_ref and p.amount == amount:
            return p  # the terminal is already waiting for this card
    await _cancel_pending_cards(order)
    _cancel_pending(order)
    terminal_id = card.get("terminal_id") or f"softpos:{device.id}"
    req = await get_terminal().start(terminal_id, amount, reference=order.token)
    shift = await open_shift_for(uow, venue.id, actor.device_id)
    payment = Payment(
        venue_id=venue.id,
        method="card",
        amount=amount,
        status="pending",
        gateway_ref=req.terminal_ref,
        shift_id=shift.id if shift else None,
        device_id=actor.device_id,
        staff_id=actor.staff_id,
    )
    order.payments.append(payment)
    order.payment_status = PaymentStatus.PENDING
    await uow.session.flush()
    await order_svc.changed(
        uow,
        order,
        "payment.card_started",
        actor,
        payment_id=payment.id,
        mode=card["mode"],
        terminal=terminal_id,
    )
    return payment


async def _cancel_pending_cards(order: Order) -> None:
    """Tell terminals to stop waiting for a card we no longer want (best effort)."""
    for p in order.payments:
        if p.method == "card" and p.status == "pending" and p.gateway_ref:
            try:
                await get_terminal().cancel(p.gateway_ref)
            except Exception:  # noqa: BLE001 - a late approval is refunded automatically anyway
                pass


async def cancel_payment(uow: UnitOfWork, order: Order, actor: Actor, payment_id: str) -> Payment:
    """Guest or staff pressed Cancel while the terminal or QR was waiting."""
    payment = next((p for p in order.payments if p.id == payment_id), None)
    if payment is None:
        raise NotFound("Payment")
    if payment.status != "pending":
        raise Conflict("not_pending", f"This payment is already {payment.status}")
    if payment.method == "card" and payment.gateway_ref:
        await get_terminal().cancel(payment.gateway_ref)
    payment.status = "cancelled"
    payment.completed_at = utcnow()
    if not any(p.status == "pending" for p in order.payments):
        order.payment_status = PaymentStatus.UNPAID
    await order_svc.changed(uow, order, "payment.cancelled", actor, payment_id=payment.id)
    return payment


async def handle_terminal_callback(uow: UnitOfWork, data: dict[str, Any]) -> Order:
    """The card processor's signed result. Source of truth, safe to receive twice."""
    ref = str(data.get("terminal_ref"))
    payment = await uow.session.scalar(
        select(Payment).where(Payment.gateway_ref == ref, Payment.method == "card")
    )
    if payment is None:
        raise NotFound("Payment")
    if data.get("status") == "succeeded" and payment.status != "succeeded" and data.get("auth_code"):
        payment.external_ref = str(data["auth_code"])[:80]
    return await _apply_callback(uow, payment, data, "Late or duplicate card payment")


# ---------------------------------------------------------------- callbacks


async def receive_callback(uow: UnitOfWork, kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """A verified bank / gateway result. For a hybrid venue whose hub is in charge, the cloud does
    not touch the order: it hands the result to the hub (the hub applies it and syncs back)."""
    method = "lankaqr" if kind == "gateway.callback" else "card"
    ref = str(data.get("gateway_ref" if method == "lankaqr" else "terminal_ref"))
    payment = await uow.session.scalar(
        select(Payment).where(Payment.gateway_ref == ref, Payment.method == method)
    )
    if payment is None:
        raise NotFound("Payment")
    venue = await uow.session.get(Venue, payment.venue_id)
    if venue is not None and await hybrid.hub_in_charge(uow, venue):
        uow.outbox(venue.id, kind, data)
        return {"ok": True, "forwarded_to_hub": True, "order_id": payment.order_id}
    handler = handle_gateway_callback if method == "lankaqr" else handle_terminal_callback
    order = await handler(uow, data)
    return {"ok": True, "order_id": order.id, "payment_status": order.payment_status}


async def handle_gateway_callback(uow: UnitOfWork, data: dict[str, Any]) -> Order:
    """The gateway's signed callback is the source of truth. Safe to receive twice."""
    ref = str(data.get("gateway_ref"))
    payment = await uow.session.scalar(
        select(Payment).where(Payment.gateway_ref == ref, Payment.method == "lankaqr")
    )
    if payment is None:
        raise NotFound("Payment")
    return await _apply_callback(uow, payment, data, "Late or duplicate QR payment")


async def _apply_callback(uow: UnitOfWork, payment: Payment, data: dict[str, Any], late_reason: str) -> Order:
    order = await order_svc.get_order(uow, payment.venue_id, payment.order_id, lock=True)
    venue = await uow.session.get(Venue, payment.venue_id)
    assert venue is not None
    actor = Actor(venue_id=venue.id)
    if payment.status == "succeeded":
        return order
    if int(data.get("amount", -1)) != payment.amount:
        raise AppError("amount_mismatch", "Callback amount does not match the payment")

    if data.get("status") == "succeeded":
        if (
            payment.status == "cancelled"
            or order.status in (Status.CANCELLED, Status.EXPIRED, Status.VOIDED)
            or order.payment_status == PaymentStatus.PAID
        ):
            # Money arrived for a payment we no longer want: accept it, then refund it.
            payment.status = "succeeded"
            payment.completed_at = utcnow()
            await _refund_payment(uow, venue, order, payment, actor, late_reason)
            await order_svc.changed(uow, order, "payment.late_refunded", actor, payment_id=payment.id)
            uow.audit(actor, "payment.late_refund", payment.id, amount=payment.amount)
            return order
        await _settle(uow, venue, order, payment, actor, drawer=False)
    else:
        if payment.status == "pending":
            payment.status = "failed"
            payment.completed_at = utcnow()
            if order.payment_status == PaymentStatus.PENDING:
                order.payment_status = PaymentStatus.UNPAID
            await order_svc.changed(uow, order, "payment.failed", actor, payment_id=payment.id)
    return order


async def _refund_payment(
    uow: UnitOfWork, venue: Venue, order: Order, charge: Payment, actor: Actor, reason: str
) -> Payment:
    shift = await open_shift_for(uow, venue.id, actor.device_id)
    external: str | None = None
    if charge.method == "cash":
        if shift is None:
            raise AppError("no_open_shift", "Cash refunds need an open cash shift on this device")
    elif charge.method == "lankaqr" and charge.gateway_ref:
        external = await get_gateway().refund(charge.gateway_ref, charge.amount)
    elif charge.method == "card" and charge.gateway_ref:
        # Paid on a connected terminal: refund through the processor. Manual card payments
        # (approval code typed in) are refunded on the bank's own terminal.
        external = await get_terminal().refund(charge.gateway_ref, charge.amount)
    refund = Payment(
        venue_id=venue.id,
        kind="refund",
        method=charge.method,
        amount=charge.amount,
        status="succeeded",
        external_ref=external,
        gateway_ref=None,
        shift_id=shift.id if shift else None,
        device_id=actor.device_id,
        staff_id=actor.staff_id,
        reason=reason,
        completed_at=utcnow(),
    )
    order.payments.append(refund)
    return refund


async def refund_all(uow: UnitOfWork, venue: Venue, order: Order, actor: Actor, reason: str) -> list[Payment]:
    if order.payment_status != PaymentStatus.PAID:
        raise Conflict("not_paid", "Only paid orders can be refunded")
    charges = [p for p in order.payments if p.kind == "charge" and p.status == "succeeded"]
    refunds = [await _refund_payment(uow, venue, order, c, actor, reason) for c in charges]
    order.paid_total = 0
    order.payment_status = PaymentStatus.REFUNDED
    if order.customer_id and order.points_earned:
        member = await uow.session.get(Customer, order.customer_id)
        if member is not None:
            loyalty.reverse(order, member)
    await uow.session.flush()
    await order_svc.changed(
        uow, order, "order.refunded", actor, reason=reason, amount=sum(r.amount for r in refunds)
    )
    uow.audit(actor, "order.refund", order.id, reason=reason, amount=sum(r.amount for r in refunds))
    return refunds
