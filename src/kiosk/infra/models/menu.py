from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiosk.infra.models.base import Base, IdMixin, TimestampMixin

# Translated text is stored as {"en": "...", "si": "...", "ta": "..."}.
# Time windows are stored as [{"days": [0..6], "start": "HH:MM", "end": "HH:MM"}], Monday = 0.
# An empty list means "always available".


class MenuCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "menu_categories"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[dict[str, Any]] = mapped_column()
    sort: Mapped[int] = mapped_column(default=0)
    windows: Mapped[list[Any]] = mapped_column(default=list)
    is_active: Mapped[bool] = mapped_column(default=True)


class MenuItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "menu_items"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("menu_categories.id"), index=True)
    name: Mapped[dict[str, Any]] = mapped_column()
    description: Mapped[dict[str, Any]] = mapped_column(default=dict)
    price: Mapped[int] = mapped_column()  # LKR cents
    # The item's code in the restaurant's own POS (PLU / SKU), when a POS is connected.
    external_code: Mapped[str | None] = mapped_column(String(40), index=True)
    station: Mapped[str] = mapped_column(String(40), default="kitchen")
    prep_minutes: Mapped[int | None] = mapped_column()  # for promised times; venue default if empty
    tax_category: Mapped[str] = mapped_column(String(40), default="food")
    allergens: Mapped[list[Any]] = mapped_column(default=list)
    image_url: Mapped[str | None] = mapped_column(String(500))
    windows: Mapped[list[Any]] = mapped_column(default=list)
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    # A combo / meal: [{"name": {...}, "item_ids": [...], "upcharges": {item_id: cents}}].
    # The guest picks one item per slot; each part goes to its own kitchen station.
    combo_slots: Mapped[list[Any]] = mapped_column(default=list)
    # "Goes well with": item ids suggested after this one is added (Manual-mode upsell rules).
    suggest_ids: Mapped[list[Any]] = mapped_column(default=list)
    # Edge-owned stock switch ("86"). Config pulls from the cloud never overwrite it.
    is_available: Mapped[bool] = mapped_column(default=True)
    availability_changed_at: Mapped[datetime | None] = mapped_column()

    modifier_groups: Mapped[list["ModifierGroup"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="ModifierGroup.sort"
    )


class ModifierGroup(IdMixin, TimestampMixin, Base):
    __tablename__ = "modifier_groups"

    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"), index=True)
    name: Mapped[dict[str, Any]] = mapped_column()
    min_select: Mapped[int] = mapped_column(default=0)
    max_select: Mapped[int] = mapped_column(default=1)
    sort: Mapped[int] = mapped_column(default=0)

    modifiers: Mapped[list["Modifier"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="Modifier.sort"
    )


class Modifier(IdMixin, TimestampMixin, Base):
    __tablename__ = "modifiers"

    group_id: Mapped[str] = mapped_column(ForeignKey("modifier_groups.id"), index=True)
    name: Mapped[dict[str, Any]] = mapped_column()
    price_delta: Mapped[int] = mapped_column(default=0)  # LKR cents, may be negative
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class PriceOffer(IdMixin, TimestampMixin, Base):
    """A temporary discount on one item (AI level 4: clear perishable stock), always within the
    owner's cap and, by default, approved by the owner first. Offers only lower prices."""

    __tablename__ = "price_offers"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    menu_item_id: Mapped[str] = mapped_column(String(26), index=True)
    discount_bp: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | active | rejected
    reason: Mapped[str] = mapped_column(String(300), default="")
    starts_at: Mapped[datetime | None] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    decided_by: Mapped[str | None] = mapped_column(String(200))


class TaxRule(IdMixin, TimestampMixin, Base):
    __tablename__ = "tax_rules"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[dict[str, Any]] = mapped_column()
    rate_bp: Mapped[int] = mapped_column()  # basis points: 1000 = 10.00%
    applies_to: Mapped[list[Any]] = mapped_column(default=lambda: ["*"])
    # compound=True: charged on the line amount plus earlier rules' charges.
    compound: Mapped[bool] = mapped_column(default=False)
    sequence: Mapped[int] = mapped_column(default=0)
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True)
