from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kiosk.infra.models.base import Base, IdMixin, TimestampMixin

DEFAULT_VENUE_SETTINGS: dict[str, Any] = {
    # "A": kitchen starts only after payment. "B": kitchen starts at once, order flagged UNPAID.
    "release_rule": "A",
    # Dine-in at tables: "pay_first" (every order paid before cooking, table locked while waiting)
    # or "tab" (rounds go straight to the kitchen and add up on one bill, paid at the end).
    "dine_in_mode": "pay_first",
    # "open": guests can order from a table screen any time. "staff_opens": a table is closed
    # (welcome screen, "call staff" only) until staff open it on the POS; closing it clears it.
    "table_access": "open",
    # Who takes ready food to the table: "self_pickup" (status board) or "waiter" (waiter screens).
    "serve_mode": "self_pickup",
    "unpaid_expiry_minutes": 10,
    "kds_warn_minutes": 8,
    "kds_late_minutes": 12,
    "default_prep_minutes": 10,
    "kitchen_cooks": 3,
    "ready_display_minutes": 15,
    "token_prefixes": {"cashier": "A", "kiosk": "K", "table": "T"},
    "languages": ["en", "si", "ta"],
    "print_kitchen_backup": False,
    # Texts to guests who leave their mobile number (needs an SMS gateway account).
    "sms_ready": True,  # "your order is ready"
    "sms_receipt": True,  # a link to the receipt after payment
    "sms_sender": "",  # sender name registered with the gateway; empty = venue name
    # Which ways guests and staff may pay. Screens hide what is off.
    "payment_methods": {"cash": True, "lankaqr": True, "card": True},
    # "cloud": screens talk to the cloud. "hybrid": screens talk to the restaurant's hub (works when
    # the internet is down), and to the cloud only if the hub is down.
    "network_mode": "cloud",
    # Equipment the installer confirmed on site (router, UPS); printers etc. are counted.
    "installed_hardware": {},
    "printers": {"receipt": {"type": "file"}, "kitchen": {"type": "file"}},
    "currency": "LKR",
    # Printed on invoices and receipts.
    "legal_name": "",
    "vat_number": "",
    "receipt_footer": "Thank you!",
    # Operating mode (BRD): "manual" or "ai". ai_level follows the Full Plan ladder:
    # 0 off, 1 insights for staff, 2 upsell to guests, 3 menu order / fast items / wait times.
    # Level 4 (prices within caps) needs inventory and is not available yet.
    # Loyalty (R-LOYAL): points per Rs 100 paid, and tiers with an automatic discount.
    "loyalty_points_per_100": 1,
    "loyalty_tiers": [
        {"name": "Silver", "min_points": 500, "discount_bp": 500},
        {"name": "Gold", "min_points": 2000, "discount_bp": 1000},
    ],
    "loyalty_consent_text": (
        "I agree that this restaurant keeps my phone number and my orders to give me points and "
        "member prices. I can ask for them to be deleted at any time."
    ),
    "mode": "manual",
    "ai_level": 1,
    # AI level 4 guardrails: the biggest discount it may offer, and whether the owner approves first.
    "ai_price_cap_bp": 1000,
    "ai_requires_approval": True,
    # Kiosk welcome screen: photos (uploaded menu media) shown one after another while idle.
    "attract_images": [],
    # The restaurant's look on every screen: main colour (#rrggbb), logo (uploaded media URL) and
    # whether screens use a light (cream) or dark background.
    "brand_color": "#f5a524",
    "logo_url": "",
    "theme": "light",
    # Overhead menu board: seconds per page.
    "board_page_seconds": 12,
}


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))


class Venue(IdMixin, TimestampMixin, Base):
    __tablename__ = "venues"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Colombo")
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # What the venue bought: {"pack", "tier", "modules": [...], "screens": {"table": 12, ...}}.
    # Empty means unrestricted (demo and development venues).
    plan: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # Bumped on every config change made in the cloud; the edge pulls when it is behind.
    config_version: Mapped[int] = mapped_column(default=1)
    sync_key_hash: Mapped[str | None] = mapped_column(String(64))

    def setting(self, key: str) -> Any:
        return {**DEFAULT_VENUE_SETTINGS, **(self.settings or {})}[key]


class Customer(IdMixin, TimestampMixin, Base):
    """A loyalty member of a restaurant group (all its branches). Kept only with consent (PDPA)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "phone"),)

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(20))  # E.164, e.g. +94771234567; None once forgotten
    name: Mapped[str | None] = mapped_column(String(120))
    consent_at: Mapped[datetime | None] = mapped_column()
    consent_text: Mapped[str | None] = mapped_column(String(500))
    points: Mapped[int] = mapped_column(default=0)
    lifetime_points: Mapped[int] = mapped_column(default=0)
    visits: Mapped[int] = mapped_column(default=0)
    last_visit_at: Mapped[datetime | None] = mapped_column()
    forgotten_at: Mapped[datetime | None] = mapped_column()


class PriceBook(Base):
    """The platform's price list for quotes: one row per module or screen type. LKR cents."""

    __tablename__ = "price_book"

    item: Mapped[str] = mapped_column(String(40), primary_key=True)  # "module:R-TABLE" | "screen:table"
    monthly: Mapped[int] = mapped_column(default=0)
    once: Mapped[int] = mapped_column(default=0)


class PlatformUser(IdMixin, TimestampMixin, Base):
    """The platform operator's own staff. They create restaurants (tenants) and support them."""

    __tablename__ = "platform_users"

    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    # 2-step login: the authenticator app's secret (encrypted), and the last code's time step used.
    totp_secret_enc: Mapped[str | None] = mapped_column(String(255))
    totp_last_step: Mapped[int | None] = mapped_column()


class AdminUser(IdMixin, TimestampMixin, Base):
    """A restaurant's owner or manager login (admin portal, owner app, screen setup)."""

    __tablename__ = "admin_users"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | manager
    is_active: Mapped[bool] = mapped_column(default=True)


STAFF_ROLES = ("cashier", "waiter", "kitchen", "manager", "owner")


class Staff(IdMixin, TimestampMixin, Base):
    __tablename__ = "staff"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    pin_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_pin_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column()


DEVICE_TYPES = ("cashier", "kds", "status", "kiosk", "table", "waiter", "board")


class Device(IdMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_token_hash", "token_hash", unique=True),
        Index("ix_devices_code_hash", "code_hash", unique=True),
    )

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    # KDS: which station this screen shows (None = all). Table: which table it sits on.
    station: Mapped[str | None] = mapped_column(String(40))
    table_ref: Mapped[str | None] = mapped_column(String(20))
    token_hash: Mapped[str | None] = mapped_column(String(64))
    pairing_code: Mapped[str | None] = mapped_column(String(6), index=True)
    # The screen code (like a Square device code): the restaurant address + this code sign a device
    # in, for good. Hash to look it up, encrypted copy so the Setup console can show it again.
    code_hash: Mapped[str | None] = mapped_column(String(64))
    code_enc: Mapped[str | None] = mapped_column(String(255))
    pairing_expires_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True)
    # Per-screen options, e.g. {"card": {"mode": "reader", "terminal_id": "PAX-001"}}.
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
