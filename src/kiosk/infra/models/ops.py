from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kiosk.infra.models.base import Base, IdMixin, TimestampMixin, utcnow


class CashShift(IdMixin, TimestampMixin, Base):
    __tablename__ = "cash_shifts"

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    device_id: Mapped[str] = mapped_column(String(26), index=True)
    opened_by: Mapped[str] = mapped_column(String(26))
    opening_float: Mapped[int] = mapped_column()
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    closed_by: Mapped[str | None] = mapped_column(String(26))
    closed_at: Mapped[datetime | None] = mapped_column()
    counted_cash: Mapped[int | None] = mapped_column()
    expected_cash: Mapped[int | None] = mapped_column()
    variance: Mapped[int | None] = mapped_column()
    report: Mapped[dict[str, Any] | None] = mapped_column()


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(60))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    device_id: Mapped[str | None] = mapped_column(String(26))
    staff_id: Mapped[str | None] = mapped_column(String(26))
    admin_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Outbox(IdMixin, Base):
    """Transactional outbox: written in the same transaction as the change it describes."""

    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_unsent", "sent_at", "created_at"),)

    venue_id: Mapped[str] = mapped_column(String(26))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column()
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))


class ServiceRequest(IdMixin, Base):
    """A guest asks for staff: call waiter, request the bill, or help at a kiosk."""

    __tablename__ = "service_requests"
    __table_args__ = (Index("ix_service_requests_open", "venue_id", "status"),)

    venue_id: Mapped[str] = mapped_column(String(26))
    device_id: Mapped[str] = mapped_column(String(26))
    kind: Mapped[str] = mapped_column(String(20))  # call_waiter | request_bill | help
    table_ref: Mapped[str | None] = mapped_column(String(20))
    where: Mapped[str] = mapped_column(String(120))  # "Table T5" / "Kiosk 1", for staff screens
    order_id: Mapped[str | None] = mapped_column(String(26))
    pay_with: Mapped[str | None] = mapped_column(String(10))  # bill requests: cash | card | qr
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | acknowledged | done
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column()
    acknowledged_by: Mapped[str | None] = mapped_column(String(26))
    done_at: Mapped[datetime | None] = mapped_column()


class AiAction(IdMixin, Base):
    """Every AI decision that changed what screens show, with the reason (Full Plan guardrail)."""

    __tablename__ = "ai_actions"
    __table_args__ = (Index("ix_ai_actions_venue_time", "venue_id", "created_at"),)

    venue_id: Mapped[str] = mapped_column(String(26))
    kind: Mapped[str] = mapped_column(String(40))  # policy | mode
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TableState(TimestampMixin, Base):
    """Is a table open for ordering? Used when the restaurant has staff open each table
    (table_access = "staff_opens"): guests can't order from an empty table's screen."""

    __tablename__ = "table_states"

    venue_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    table_ref: Mapped[str] = mapped_column(String(20), primary_key=True)
    is_open: Mapped[bool] = mapped_column(default=False)
    opened_at: Mapped[datetime | None] = mapped_column()
    opened_by: Mapped[str | None] = mapped_column(String(26))  # staff id
    closed_at: Mapped[datetime | None] = mapped_column()
    # A visit: guests are at the table from their first order until they leave. Then the table needs
    # cleaning before the next guests; a waiter marks it cleaned.
    occupied_since: Mapped[datetime | None] = mapped_column()
    needs_cleaning: Mapped[bool] = mapped_column(default=False)
    cleaned_at: Mapped[datetime | None] = mapped_column()
    cleaned_by: Mapped[str | None] = mapped_column(String(26))


class Feedback(IdMixin, Base):
    """What guests thought, from the table (or kiosk) after eating: stars, quick tags, a comment."""

    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_venue_time", "venue_id", "created_at"),)

    venue_id: Mapped[str] = mapped_column(String(26))
    device_id: Mapped[str | None] = mapped_column(String(26))
    table_ref: Mapped[str | None] = mapped_column(String(20))
    order_id: Mapped[str | None] = mapped_column(String(26), index=True)
    rating: Mapped[int] = mapped_column()  # 1-5
    tags: Mapped[list[Any]] = mapped_column(default=list)  # e.g. ["food", "fast"] or ["slow"]
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    seen_at: Mapped[datetime | None] = mapped_column()
    seen_by: Mapped[str | None] = mapped_column(String(26))


class SmsMessage(IdMixin, TimestampMixin, Base):
    """A text to a guest: "your order is ready", or a receipt link. Queued first, so a hub without
    internet sends it as soon as it can."""

    __tablename__ = "sms_messages"
    __table_args__ = (Index("ix_sms_status", "status", "created_at"),)

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    order_id: Mapped[str | None] = mapped_column(String(26))
    phone: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))  # ready | receipt
    text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | sent | failed
    attempts: Mapped[int] = mapped_column(default=0)
    provider_ref: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column()


class StockItem(IdMixin, TimestampMixin, Base):
    """Portions of a menu item in stock (R-INV). Sold portions are taken off when cooking starts."""

    __tablename__ = "stock_items"
    __table_args__ = (UniqueConstraint("venue_id", "menu_item_id"),)

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    menu_item_id: Mapped[str] = mapped_column(String(26))
    on_hand: Mapped[int] = mapped_column(default=0)
    low_at: Mapped[int] = mapped_column(default=5)  # "low stock" alert at or below this
    auto_86: Mapped[bool] = mapped_column(default=True)  # sold out on every screen at zero
    auto_off: Mapped[bool] = mapped_column(default=False)  # it was switched off by stock, not by staff
    perishable_until: Mapped[datetime | None] = mapped_column()  # use-by time of the current batch


class StockMove(IdMixin, Base):
    __tablename__ = "stock_moves"
    __table_args__ = (Index("ix_stock_moves_venue_time", "venue_id", "created_at"),)

    venue_id: Mapped[str] = mapped_column(String(26))
    menu_item_id: Mapped[str] = mapped_column(String(26))
    change: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(20))  # sale | delivery | count | waste | void_return
    order_id: Mapped[str | None] = mapped_column(String(26))
    by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(120))  # venue + endpoint
    key: Mapped[str] = mapped_column(String(100))
    status_code: Mapped[int] = mapped_column()
    response: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
