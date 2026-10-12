"""Texts to guests who leave their mobile number on the kiosk, table screen or at the cashier.

  ready    "Your order K007 at Demo Café is ready." when the kitchen finishes (if sms_ready)
  receipt  a private link to the receipt after payment (if sms_receipt)

Messages are queued and sent after the transaction commits. If the gateway can't be reached (a
hub without internet) they stay queued and the background job retries them. The number is kept
only on that order, for that purpose.
"""

import hashlib
import hmac
from typing import Any

import structlog
from sqlalchemy import select

from kiosk.config import settings
from kiosk.infra.db import session_factory
from kiosk.infra.models import Order, SmsMessage, Venue, utcnow
from kiosk.infra.sms import SmsError, get_sms
from kiosk.services.uow import UnitOfWork

log = structlog.get_logger()
MAX_ATTEMPTS = 5


def receipt_ref(order_id: str) -> str:
    sig = hmac.new(settings.jwt_secret.encode(), f"receipt:{order_id}".encode(), hashlib.sha256).hexdigest()
    return f"{order_id}.{sig[:20]}"


def order_from_ref(ref: str) -> str | None:
    order_id, _, _ = ref.partition(".")
    return order_id if hmac.compare_digest(receipt_ref(order_id), ref) else None


def receipt_url(order: Order) -> str:
    return f"{(settings.public_url or '').rstrip('/')}/v1/receipts/{receipt_ref(order.id)}"


def _text(venue: Venue, order: Order, kind: str) -> str:
    if kind == "ready":
        where = (
            "Please collect it at the counter" if not order.table_ref else "It is on its way to your table"
        )
        return f"{venue.name}: your order {order.token} is ready. {where}."
    return f"{venue.name}: thank you! Your receipt for order {order.token}: {receipt_url(order)}"


async def queue(uow: UnitOfWork, venue: Venue, order: Order, kind: str) -> SmsMessage | None:
    setting = {"ready": "sms_ready", "receipt": "sms_receipt"}[kind]
    if not order.notify_phone or not venue.setting(setting):
        return None
    already = await uow.session.scalar(
        select(SmsMessage.id).where(SmsMessage.order_id == order.id, SmsMessage.kind == kind)
    )
    if already:
        return None
    msg = SmsMessage(
        venue_id=venue.id,
        order_id=order.id,
        phone=order.notify_phone,
        kind=kind,
        text=_text(venue, order, kind)[:500],
        status="queued",
        attempts=0,
    )
    uow.session.add(msg)
    await uow.session.flush()
    msg_id = msg.id
    uow.after_commit.append(lambda: deliver(msg_id))
    return msg


async def deliver(msg_id: str) -> None:
    async with session_factory()() as session:
        msg = await session.get(SmsMessage, msg_id)
        if msg is None or msg.status == "sent":
            return
        venue = await session.get(Venue, msg.venue_id)
        sender = str((venue and venue.setting("sms_sender")) or (venue.name if venue else "Kiosk"))[:11]
        msg.attempts += 1
        try:
            msg.provider_ref = await get_sms().send(msg.phone, msg.text, sender)
            msg.status, msg.sent_at, msg.error = "sent", utcnow(), None
        except SmsError as exc:
            msg.error = str(exc)[:300]
            msg.status = "failed" if msg.attempts >= MAX_ATTEMPTS else "queued"
        except Exception as exc:  # noqa: BLE001 - no internet on a hub: try again later
            msg.error = str(exc)[:300]
            msg.status = "failed" if msg.attempts >= MAX_ATTEMPTS else "queued"
        await session.commit()


async def retry_queued() -> int:
    async with session_factory()() as session:
        ids = (
            await session.scalars(
                select(SmsMessage.id)
                .where(SmsMessage.status == "queued")
                .order_by(SmsMessage.created_at)
                .limit(50)
            )
        ).all()
    for msg_id in ids:
        await deliver(msg_id)
    return len(ids)


def sms_dict(m: SmsMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "kind": m.kind,
        "phone": m.phone[:-4] + "••••" if len(m.phone) > 4 else m.phone,
        "status": m.status,
        "error": m.error,
        "created_at": m.created_at.isoformat(),
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }
