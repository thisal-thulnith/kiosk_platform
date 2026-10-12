from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiosk.infra.models.base import Base, IdMixin, TimestampMixin, utcnow

# Transactional tables deliberately hold no foreign keys to config tables (menu, staff,
# devices). They keep snapshots instead, so a config pull can replace menu rows freely.


class Order(IdMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_venue_status", "venue_id", "status"),
        Index("ix_orders_venue_date_token", "venue_id", "business_date", "token"),
    )

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    token: Mapped[str] = mapped_column(String(12))
    business_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, venue local time
    channel: Mapped[str] = mapped_column(String(20))  # cashier | kiosk | table
    table_ref: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    payment_status: Mapped[str] = mapped_column(String(20))
    release_rule: Mapped[str] = mapped_column(String(1))
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # normal | vip | rush
    promised_at: Mapped[datetime | None] = mapped_column()  # "ready in about N minutes"
    is_tab: Mapped[bool] = mapped_column(default=False)  # dine-in open bill: rounds added, paid at the end
    served_at: Mapped[datetime | None] = mapped_column()  # a waiter took the ready food to the table
    # One payment at a time: who opened "Take payment" for this order, until when (others wait).
    pay_hold_by: Mapped[str | None] = mapped_column(String(26))
    pay_hold_name: Mapped[str | None] = mapped_column(String(120))
    pay_hold_until: Mapped[datetime | None] = mapped_column()
    # Loyalty: the member, their tier discount (applied before service charge and taxes), points.
    customer_id: Mapped[str | None] = mapped_column(String(26), index=True)
    discount_bp: Mapped[int] = mapped_column(default=0)
    discount_label: Mapped[str | None] = mapped_column(String(80))
    discount_total: Mapped[int] = mapped_column(default=0)
    points_earned: Mapped[int] = mapped_column(default=0)
    # The guest's mobile for "your order is ready" (and receipt) texts, only for this order.
    notify_phone: Mapped[str | None] = mapped_column(String(20))
    subtotal: Mapped[int] = mapped_column(default=0)
    tax_total: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    paid_total: Mapped[int] = mapped_column(default=0)
    tax_lines: Mapped[list[Any]] = mapped_column(default=list)
    notes: Mapped[str | None] = mapped_column(String(500))
    device_id: Mapped[str | None] = mapped_column(String(26))
    placed_by_staff_id: Mapped[str | None] = mapped_column(String(26))
    expires_at: Mapped[datetime | None] = mapped_column()
    released_at: Mapped[datetime | None] = mapped_column()
    ready_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    # Bumped on every change. The cloud keeps the highest version it has seen.
    version: Mapped[int] = mapped_column(default=1)

    items: Mapped[list["OrderItem"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="OrderItem.position"
    )
    payments: Mapped[list["Payment"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="Payment.created_at"
    )


class OrderItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    menu_item_id: Mapped[str] = mapped_column(String(26))
    name: Mapped[dict[str, Any]] = mapped_column()
    unit_price: Mapped[int] = mapped_column()  # base price + modifier deltas
    quantity: Mapped[int] = mapped_column()
    modifiers: Mapped[list[Any]] = mapped_column(default=list)
    notes: Mapped[str | None] = mapped_column(String(300))
    allergens: Mapped[list[Any]] = mapped_column(default=list)
    line_total: Mapped[int] = mapped_column()
    station: Mapped[str] = mapped_column(String(40))
    tax_category: Mapped[str] = mapped_column(String(40))
    kds_status: Mapped[str] = mapped_column(String(20), default="queued")
    # Part of a combo: the position of the combo line in the same order (None for normal lines).
    parent_position: Mapped[int | None] = mapped_column()
    remake_count: Mapped[int] = mapped_column(default=0)
    source: Mapped[str | None] = mapped_column(String(20))  # "upsell" when added from a suggestion
    started_at: Mapped[datetime | None] = mapped_column()
    done_at: Mapped[datetime | None] = mapped_column()


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="charge")  # charge | refund
    method: Mapped[str] = mapped_column(String(20))  # cash | card | lankaqr
    amount: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))  # pending | succeeded | failed | cancelled
    tendered: Mapped[int | None] = mapped_column()
    change_given: Mapped[int | None] = mapped_column()
    gateway_ref: Mapped[str | None] = mapped_column(String(80), index=True)
    qr_payload: Mapped[str | None] = mapped_column(String(1000))
    external_ref: Mapped[str | None] = mapped_column(String(80))
    shift_id: Mapped[str | None] = mapped_column(String(26), index=True)
    device_id: Mapped[str | None] = mapped_column(String(26))  # the screen that took the payment
    staff_id: Mapped[str | None] = mapped_column(String(26))
    reason: Mapped[str | None] = mapped_column(String(300))
    completed_at: Mapped[datetime | None] = mapped_column()


class OrderEvent(IdMixin, Base):
    """Append-only history of everything that happened to an order."""

    __tablename__ = "order_events"

    order_id: Mapped[str] = mapped_column(String(26), index=True)
    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    device_id: Mapped[str | None] = mapped_column(String(26))
    staff_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Invoice(IdMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("venue_id", "number"),)

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    order_id: Mapped[str] = mapped_column(String(26), unique=True)
    number: Mapped[str] = mapped_column(String(40))
    total: Mapped[int] = mapped_column()
    snapshot: Mapped[dict[str, Any]] = mapped_column()
    issued_at: Mapped[datetime] = mapped_column(default=utcnow)


class Counter(Base):
    """Gapless sequences: daily token numbers and invoice numbers."""

    __tablename__ = "counters"

    venue_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
