from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from kiosk.api.deps import Admin, AdminVenue, Uow
from kiosk.api.routers.admin_org import bump_config
from kiosk.domain.menu import validate_windows
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import MenuCategory, MenuItem, Modifier, ModifierGroup, TaxRule
from kiosk.services.serializers import category_dict, menu_item_dict, tax_rule_dict

router = APIRouter(prefix="/v1/admin/venues/{venue_id}", tags=["admin: menu"])

Text = dict[str, str]  # {"en": ..., "si": ..., "ta": ...}


def _check_text(value: Text) -> Text:
    if not value.get("en"):
        raise ValueError("English text ('en') is required")
    return value


def _check_windows(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        validate_windows(value)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid time window: {exc}") from exc
    return value


class CategoryIn(BaseModel):
    name: Text
    sort: int = 0
    windows: list[dict[str, Any]] = []
    is_active: bool = True

    _name = field_validator("name")(_check_text)
    _windows = field_validator("windows")(_check_windows)


@router.get("/menu/categories")
async def list_categories(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(MenuCategory).where(MenuCategory.venue_id == venue.id).order_by(MenuCategory.sort)
        )
    ).all()
    return [category_dict(c) for c in rows]


@router.post("/menu/categories", status_code=201)
async def create_category(body: CategoryIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    cat = MenuCategory(venue_id=venue.id, **body.model_dump())
    uow.session.add(cat)
    bump_config(venue)
    await uow.commit()
    return category_dict(cat)


@router.put("/menu/categories/{category_id}")
async def update_category(
    category_id: str, body: CategoryIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    cat = await uow.session.get(MenuCategory, category_id)
    if cat is None or cat.venue_id != venue.id:
        raise NotFound("Category")
    for k, v in body.model_dump().items():
        setattr(cat, k, v)
    bump_config(venue)
    await uow.commit()
    return category_dict(cat)


class ModifierIn(BaseModel):
    id: str | None = None  # keep the id when editing, so existing carts stay valid
    name: Text
    price_delta: int = 0
    sort: int = 0
    is_active: bool = True

    _name = field_validator("name")(_check_text)


class ModifierGroupIn(BaseModel):
    id: str | None = None
    name: Text
    min_select: int = Field(0, ge=0)
    max_select: int = Field(1, ge=1)
    sort: int = 0
    modifiers: list[ModifierIn] = []

    _name = field_validator("name")(_check_text)


class ComboSlotIn(BaseModel):
    name: Text
    item_ids: list[str] = Field(min_length=1, description="Items the guest can pick for this part")
    upcharges: dict[str, int] = Field(default={}, description="item id -> extra LKR cents (e.g. large drink)")

    _name = field_validator("name")(_check_text)


class ItemIn(BaseModel):
    category_id: str
    name: Text
    description: dict[str, str] = {}
    price: int = Field(ge=0, description="LKR cents")
    external_code: str | None = Field(
        None, max_length=40, description="PLU / SKU in the restaurant's own POS"
    )
    station: str = "kitchen"
    prep_minutes: int | None = Field(default=None, ge=1, le=240, description="Typical cooking minutes")
    tax_category: str = "food"
    allergens: list[str] = []
    image_url: str | None = None
    windows: list[dict[str, Any]] = []
    sort: int = 0
    is_active: bool = True
    modifier_groups: list[ModifierGroupIn] = []
    combo_slots: list[ComboSlotIn] = Field(default=[], description="Makes this item a combo / meal")
    suggest_ids: list[str] = Field(default=[], max_length=6, description="'Goes well with' suggestions")

    _name = field_validator("name")(_check_text)
    _windows = field_validator("windows")(_check_windows)


async def _check_suggestions(uow: Uow, venue_id: str, ids: list[str], item_id: str | None) -> list[str]:
    if not ids:
        return []
    found = set(
        (
            await uow.session.scalars(
                select(MenuItem.id).where(MenuItem.venue_id == venue_id, MenuItem.id.in_(ids))
            )
        ).all()
    )
    if set(ids) - found or item_id in ids:
        raise AppError("bad_suggestion", "Suggestions must be other items on this venue's menu")
    return list(dict.fromkeys(ids))


async def _check_combo(uow: Uow, venue_id: str, body: ItemIn, item_id: str | None) -> list[dict[str, Any]]:
    ids = {i for s in body.combo_slots for i in s.item_ids}
    if not ids:
        return []
    parts = {
        i.id: i
        for i in (
            await uow.session.scalars(
                select(MenuItem).where(MenuItem.venue_id == venue_id, MenuItem.id.in_(ids))
            )
        ).all()
    }
    if set(ids) - set(parts):
        raise AppError("bad_combo", "A combo part is not on this venue's menu")
    if item_id in ids or any(p.combo_slots for p in parts.values()):
        raise AppError("bad_combo", "A combo cannot contain itself or another combo")
    for s in body.combo_slots:
        if set(s.upcharges) - set(s.item_ids) or any(v < 0 for v in s.upcharges.values()):
            raise AppError("bad_combo", "Upcharges must be for items in the same part and not negative")
    return [s.model_dump() for s in body.combo_slots]


def _build_groups(groups: list[ModifierGroupIn]) -> list[ModifierGroup]:
    built = []
    for g in groups:
        if g.min_select > g.max_select:
            raise AppError("bad_modifier_group", "min_select cannot be above max_select")
        group = ModifierGroup(
            name=g.name,
            min_select=g.min_select,
            max_select=g.max_select,
            sort=g.sort,
            modifiers=[
                Modifier(
                    name=m.name,
                    price_delta=m.price_delta,
                    sort=m.sort,
                    is_active=m.is_active,
                    **({"id": m.id} if m.id else {}),
                )
                for m in g.modifiers
            ],
        )
        if g.id:
            group.id = g.id
        built.append(group)
    return built


async def _check_category(uow: Uow, venue_id: str, category_id: str) -> None:
    cat = await uow.session.get(MenuCategory, category_id)
    if cat is None or cat.venue_id != venue_id:
        raise AppError("bad_category", "Category not found in this venue")


@router.get("/menu/items")
async def list_items(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(MenuItem).where(MenuItem.venue_id == venue.id).order_by(MenuItem.sort)
        )
    ).all()
    return [menu_item_dict(i) for i in rows]


@router.post("/menu/items", status_code=201)
async def create_item(body: ItemIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    await _check_category(uow, venue.id, body.category_id)
    data = body.model_dump(exclude={"modifier_groups", "combo_slots", "suggest_ids"})
    slots = await _check_combo(uow, venue.id, body, None)
    suggest = await _check_suggestions(uow, venue.id, body.suggest_ids, None)
    item = MenuItem(
        venue_id=venue.id,
        **data,
        combo_slots=slots,
        suggest_ids=suggest,
        modifier_groups=_build_groups(body.modifier_groups),
    )
    uow.session.add(item)
    bump_config(venue)
    uow.audit(admin.actor(venue.id), "menu.item_create", None, name=body.name["en"], price=body.price)
    await uow.commit()
    return menu_item_dict(item)


@router.put("/menu/items/{item_id}")
async def update_item(
    item_id: str, body: ItemIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    item = await uow.session.get(MenuItem, item_id)
    if item is None or item.venue_id != venue.id:
        raise NotFound("Menu item")
    await _check_category(uow, venue.id, body.category_id)
    old_price = item.price
    item.combo_slots = await _check_combo(uow, venue.id, body, item.id)
    item.suggest_ids = await _check_suggestions(uow, venue.id, body.suggest_ids, item.id)
    for k, v in body.model_dump(exclude={"modifier_groups", "combo_slots", "suggest_ids"}).items():
        setattr(item, k, v)
    # Replace groups in two steps so re-used ids don't collide inside one flush.
    item.modifier_groups = []
    await uow.session.flush()
    item.modifier_groups = _build_groups(body.modifier_groups)
    bump_config(venue)
    if old_price != body.price:
        uow.audit(admin.actor(venue.id), "menu.price_change", item.id, old=old_price, new=body.price)
    await uow.commit()
    return menu_item_dict(item)


# ------------------------------------------------------------------ tax rules


class TaxRuleIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: Text
    rate_bp: int = Field(ge=0, le=10_000, description="Basis points: 1000 = 10%")
    applies_to: list[str] = ["*"]
    compound: bool = False
    sequence: int = 0
    effective_from: datetime
    effective_to: datetime | None = None
    is_active: bool = True

    _name = field_validator("name")(_check_text)

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Include a timezone, e.g. 2026-01-01T00:00:00+05:30")
        return v


@router.get("/tax-rules")
async def list_tax_rules(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(TaxRule).where(TaxRule.venue_id == venue.id).order_by(TaxRule.sequence)
        )
    ).all()
    return [tax_rule_dict(r) for r in rows]


@router.post("/tax-rules", status_code=201)
async def create_tax_rule(body: TaxRuleIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    if body.effective_to and body.effective_to <= body.effective_from:
        raise AppError("bad_dates", "effective_to must be after effective_from")
    rule = TaxRule(venue_id=venue.id, **body.model_dump())
    uow.session.add(rule)
    bump_config(venue)
    uow.audit(admin.actor(venue.id), "tax.create", None, code=body.code, rate_bp=body.rate_bp)
    await uow.commit()
    return tax_rule_dict(rule)


@router.put("/tax-rules/{rule_id}")
async def update_tax_rule(
    rule_id: str, body: TaxRuleIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    """Prefer ending a rule (effective_to) and adding a new one over editing rates in place,
    so past orders stay explainable."""
    rule = await uow.session.get(TaxRule, rule_id)
    if rule is None or rule.venue_id != venue.id:
        raise NotFound("Tax rule")
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    bump_config(venue)
    uow.audit(admin.actor(venue.id), "tax.update", rule.id, **body.model_dump(mode="json"))
    await uow.commit()
    return tax_rule_dict(rule)
