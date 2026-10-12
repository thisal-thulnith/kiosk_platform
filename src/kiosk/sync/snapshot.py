"""Converting between database rows and sync payloads (cloud <-> the restaurant's hub).

Direction of ownership:
  cloud -> hub:  "config", versioned: venue settings and package, staff, menu, tax rules, screens
                 (with their key hashes, so tablets log in to the hub), printers, stock settings,
                 approved deals
  both ways:     orders, invoices, shifts, stock moves and sold-out switches, through each side's
                 outbox. The hub pushes its changes; it pulls the cloud's (payments the bank
                 confirmed at the cloud, orders taken on the cloud while the hub was down).
                 Order snapshots carry a version: an older one never overwrites a newer one.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.infra.models import (
    CashShift,
    Device,
    Invoice,
    MenuCategory,
    MenuItem,
    Modifier,
    ModifierGroup,
    Order,
    OrderItem,
    Payment,
    PriceOffer,
    Printer,
    Staff,
    StockItem,
    StockMove,
    TaxRule,
    Tenant,
    Venue,
)
from kiosk.services.serializers import category_dict, menu_item_dict, tax_rule_dict


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# ------------------------------------------------------------------ config (cloud -> edge)


async def build_config(session: AsyncSession, venue: Venue) -> dict[str, Any]:
    tenant = await session.get(Tenant, venue.tenant_id)
    staff = (await session.scalars(select(Staff).where(Staff.venue_id == venue.id))).all()
    cats = (await session.scalars(select(MenuCategory).where(MenuCategory.venue_id == venue.id))).all()
    items = (await session.scalars(select(MenuItem).where(MenuItem.venue_id == venue.id))).all()
    rules = (await session.scalars(select(TaxRule).where(TaxRule.venue_id == venue.id))).all()
    devices = (await session.scalars(select(Device).where(Device.venue_id == venue.id))).all()
    printers = (await session.scalars(select(Printer).where(Printer.venue_id == venue.id))).all()
    stock = (await session.scalars(select(StockItem).where(StockItem.venue_id == venue.id))).all()
    offers = (
        await session.scalars(
            select(PriceOffer).where(PriceOffer.venue_id == venue.id, PriceOffer.status == "active")
        )
    ).all()
    return {
        "config_version": venue.config_version,
        "tenant": {"id": venue.tenant_id, "name": tenant.name if tenant else ""},
        "venue": {
            "id": venue.id,
            "name": venue.name,
            "code": venue.code,
            "timezone": venue.timezone,
            "settings": venue.settings,
        },
        # PIN hashes travel so staff can log in while the edge is offline.
        "staff": [
            {"id": s.id, "name": s.name, "role": s.role, "pin_hash": s.pin_hash, "is_active": s.is_active}
            for s in staff
        ],
        "categories": [category_dict(c) for c in cats],
        "items": [menu_item_dict(i) for i in items],
        "tax_rules": [tax_rule_dict(r) for r in rules],
        "plan": venue.plan,
        # Key hashes only: the hub can check a tablet's key, never learn it.
        "devices": [
            {
                "id": d.id,
                "type": d.type,
                "name": d.name,
                "station": d.station,
                "table_ref": d.table_ref,
                "token_hash": d.token_hash,
                "is_active": d.is_active,
                "settings": d.settings,
            }
            for d in devices
        ],
        "printers": [
            {
                k: getattr(p, k)
                for k in (
                    "id",
                    "name",
                    "connection",
                    "roles",
                    "stations",
                    "device_id",
                    "host",
                    "port",
                    "paper_mm",
                    "cash_drawer",
                    "token_digest",
                    "is_active",
                )
            }
            | {"tested_at": _iso(p.tested_at)}
            for p in printers
        ],
        "stock": [
            {
                "menu_item_id": x.menu_item_id,
                "low_at": x.low_at,
                "auto_86": x.auto_86,
                "perishable_until": _iso(x.perishable_until),
            }
            for x in stock
        ],
        "offers": [
            {
                "id": o.id,
                "menu_item_id": o.menu_item_id,
                "discount_bp": o.discount_bp,
                "reason": o.reason,
                "starts_at": _iso(o.starts_at),
                "ends_at": _iso(o.ends_at),
                "decided_by": o.decided_by,
            }
            for o in offers
        ],
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def apply_config(session: AsyncSession, cfg: dict[str, Any]) -> None:
    """Make the edge's config match the cloud's. Stock switches (is_available) stay local."""
    v = cfg["venue"]
    if await session.get(Tenant, cfg["tenant"]["id"]) is None:
        session.add(Tenant(id=cfg["tenant"]["id"], name=cfg["tenant"]["name"]))
    venue = await session.get(Venue, v["id"])
    if venue is None:
        venue = Venue(id=v["id"], tenant_id=cfg["tenant"]["id"], code=v["code"], name=v["name"])
        session.add(venue)
    venue.name, venue.code, venue.timezone = v["name"], v["code"], v["timezone"]
    venue.settings = v["settings"] or {}
    venue.config_version = cfg["config_version"]
    if "plan" in cfg:
        venue.plan = cfg["plan"]

    seen: set[str] = set()
    for s in cfg["staff"]:
        seen.add(s["id"])
        staff = await session.get(Staff, s["id"]) or Staff(id=s["id"], venue_id=venue.id)
        staff.name, staff.role, staff.pin_hash = s["name"], s["role"], s["pin_hash"]
        staff.is_active = s["is_active"]
        session.add(staff)
    await _deactivate(session, Staff, venue.id, seen)

    seen = set()
    for c in cfg["categories"]:
        seen.add(c["id"])
        cat = await session.get(MenuCategory, c["id"]) or MenuCategory(id=c["id"], venue_id=venue.id)
        cat.name, cat.sort, cat.windows, cat.is_active = c["name"], c["sort"], c["windows"], c["is_active"]
        session.add(cat)
    await _deactivate(session, MenuCategory, venue.id, seen)
    await session.flush()

    seen = set()
    for i in cfg["items"]:
        seen.add(i["id"])
        item = await session.get(MenuItem, i["id"])
        if item is None:
            item = MenuItem(id=i["id"], venue_id=venue.id, is_available=True)
            session.add(item)
        for k in (
            "category_id",
            "name",
            "description",
            "price",
            "station",
            "tax_category",
            "allergens",
            "image_url",
            "windows",
            "sort",
            "is_active",
        ):
            setattr(item, k, i[k])
        item.external_code = i.get("external_code")
        item.modifier_groups = []
        await session.flush()
        item.modifier_groups = [
            ModifierGroup(
                id=g["id"],
                name=g["name"],
                min_select=g["min_select"],
                max_select=g["max_select"],
                sort=g["sort"],
                modifiers=[
                    Modifier(
                        id=m["id"],
                        name=m["name"],
                        price_delta=m["price_delta"],
                        sort=m["sort"],
                        is_active=m["is_active"],
                    )
                    for m in g["modifiers"]
                ],
            )
            for g in i["modifier_groups"]
        ]
    await _deactivate(session, MenuItem, venue.id, seen)

    seen = set()
    for r in cfg["tax_rules"]:
        seen.add(r["id"])
        rule = await session.get(TaxRule, r["id"]) or TaxRule(id=r["id"], venue_id=venue.id)
        rule.code, rule.name, rule.rate_bp = r["code"], r["name"], r["rate_bp"]
        rule.applies_to, rule.compound, rule.sequence = r["applies_to"], r["compound"], r["sequence"]
        rule.effective_from = datetime.fromisoformat(r["effective_from"])
        rule.effective_to = _dt(r["effective_to"])
        rule.is_active = r["is_active"]
        session.add(rule)
    await _deactivate(session, TaxRule, venue.id, seen)
    await session.flush()
    await _apply_devices_and_printers(session, venue.id, cfg)


async def _apply_devices_and_printers(session: AsyncSession, venue_id: str, cfg: dict[str, Any]) -> None:
    seen: set[str] = set()
    for d in cfg.get("devices", []):
        seen.add(d["id"])
        dev = await session.get(Device, d["id"]) or Device(id=d["id"], venue_id=venue_id)
        for k in ("type", "name", "station", "table_ref", "token_hash", "is_active", "settings"):
            setattr(dev, k, d[k])
        session.add(dev)
    if "devices" in cfg:
        await _deactivate(session, Device, venue_id, seen)
        await session.flush()
    seen = set()
    for p in cfg.get("printers", []):
        seen.add(p["id"])
        printer = await session.get(Printer, p["id"]) or Printer(
            id=p["id"], venue_id=venue_id, last_status={}
        )
        for k in ("name", "connection", "roles", "stations", "device_id", "paper_mm", "cash_drawer"):
            setattr(printer, k, p[k])
        printer.host, printer.port = p.get("host"), p.get("port") or 9100
        printer.token_digest, printer.is_active = p["token_digest"], p["is_active"]
        printer.tested_at = _dt(p["tested_at"])
        session.add(printer)
    if "printers" in cfg:
        await _deactivate(session, Printer, venue_id, seen)
    for x in cfg.get("stock", []):
        item = await session.scalar(
            select(StockItem).where(
                StockItem.venue_id == venue_id, StockItem.menu_item_id == x["menu_item_id"]
            )
        )
        if item is None:  # the count itself arrives as stock moves
            item = StockItem(venue_id=venue_id, menu_item_id=x["menu_item_id"], on_hand=0, auto_off=False)
            session.add(item)
        item.low_at, item.auto_86 = x["low_at"], x["auto_86"]
        item.perishable_until = _dt(x["perishable_until"])
    live = {o["id"] for o in cfg.get("offers", [])}
    for o in cfg.get("offers", []):
        offer = await session.get(PriceOffer, o["id"]) or PriceOffer(id=o["id"], venue_id=venue_id)
        offer.menu_item_id, offer.discount_bp, offer.reason = o["menu_item_id"], o["discount_bp"], o["reason"]
        offer.starts_at, offer.ends_at = _dt(o["starts_at"]), _dt(o["ends_at"])  # type: ignore[assignment]
        offer.decided_by, offer.status = o["decided_by"], "active"
        session.add(offer)
    if "offers" in cfg:  # deals stopped at the cloud stop here too
        for offer in (
            await session.scalars(
                select(PriceOffer).where(PriceOffer.venue_id == venue_id, PriceOffer.status == "active")
            )
        ).all():
            if offer.id not in live:
                offer.status = "rejected"
    await session.flush()


async def _deactivate(session: AsyncSession, model: Any, venue_id: str, keep: set[str]) -> None:
    rows: list[Any] = list((await session.scalars(select(model).where(model.venue_id == venue_id))).all())
    for row in rows:
        if row.id not in keep:
            row.is_active = False


# ------------------------------------------------------------------ records (edge -> cloud)

_ORDER_FIELDS = (
    "token",
    "business_date",
    "channel",
    "table_ref",
    "status",
    "payment_status",
    "release_rule",
    "subtotal",
    "tax_total",
    "total",
    "paid_total",
    "tax_lines",
    "notes",
    "device_id",
    "placed_by_staff_id",
    "priority",
    "is_tab",
    "customer_id",
    "discount_bp",
    "discount_total",
    "discount_label",
    "points_earned",
    "notify_phone",
)
_ORDER_TIMES = (
    "expires_at",
    "released_at",
    "ready_at",
    "completed_at",
    "created_at",
    "updated_at",
    "served_at",
    "promised_at",
)


async def ingest_order(session: AsyncSession, venue_id: str, snap: dict[str, Any]) -> bool:
    """Upsert an order snapshot. Older versions than the stored one are ignored."""
    order = await session.get(Order, snap["id"])
    if order is not None and order.version >= snap["version"]:
        return False
    if order is None:
        order = Order(id=snap["id"], venue_id=venue_id, items=[], payments=[])
        session.add(order)
    for k in _ORDER_FIELDS:
        if k in snap:
            setattr(order, k, snap[k])
    for k in _ORDER_TIMES:
        setattr(order, k, _dt(snap.get(k)))
    order.version = snap["version"]
    order.items = []
    order.payments = []
    await session.flush()
    order.items = [
        OrderItem(
            id=i["id"],
            position=i["position"],
            menu_item_id=i["menu_item_id"],
            name=i["name"],
            unit_price=i["unit_price"],
            quantity=i["quantity"],
            modifiers=i["modifiers"],
            notes=i["notes"],
            allergens=i["allergens"],
            line_total=i["line_total"],
            station=i["station"],
            tax_category=i["tax_category"],
            kds_status=i["kds_status"],
            parent_position=i.get("parent_position"),
            remake_count=i.get("remake_count", 0),
            source=i.get("source"),
            started_at=_dt(i["started_at"]),
            done_at=_dt(i["done_at"]),
        )
        for i in snap["items"]
    ]
    order.payments = [
        Payment(
            id=p["id"],
            venue_id=venue_id,
            kind=p["kind"],
            method=p["method"],
            amount=p["amount"],
            status=p["status"],
            tendered=p["tendered"],
            change_given=p["change_given"],
            gateway_ref=p["gateway_ref"],
            external_ref=p["external_ref"],
            shift_id=p["shift_id"],
            staff_id=p["staff_id"],
            device_id=p.get("device_id"),
            reason=p["reason"],
            completed_at=_dt(p["completed_at"]),
            created_at=_dt(p["created_at"]),
        )
        for p in snap["payments"]
    ]
    await session.flush()
    return True


async def ingest_invoice(session: AsyncSession, venue_id: str, data: dict[str, Any]) -> bool:
    if await session.scalar(select(Invoice.id).where(Invoice.order_id == data["order_id"])):
        return False
    session.add(
        Invoice(
            id=data["id"],
            venue_id=venue_id,
            order_id=data["order_id"],
            number=data["number"],
            total=data["total"],
            snapshot=data["snapshot"],
            issued_at=_dt(data["issued_at"]),
        )
    )
    return True


async def ingest_shift(session: AsyncSession, venue_id: str, data: dict[str, Any]) -> bool:
    shift = await session.get(CashShift, data["id"]) or CashShift(id=data["id"], venue_id=venue_id)
    for k in (
        "device_id",
        "opened_by",
        "opening_float",
        "closed_by",
        "counted_cash",
        "expected_cash",
        "variance",
        "report",
    ):
        setattr(shift, k, data[k])
    shift.opened_at = datetime.fromisoformat(data["opened_at"])
    shift.closed_at = _dt(data["closed_at"])
    session.add(shift)
    return True


async def ingest_availability(session: AsyncSession, venue_id: str, data: dict[str, Any]) -> bool:
    item = await session.get(MenuItem, data["item_id"])
    if item is None or item.venue_id != venue_id:
        return False
    item.is_available = data["is_available"]
    return True


async def ingest_stock_move(session: AsyncSession, venue_id: str, data: dict[str, Any]) -> bool:
    """Apply a stock move made on the other side, once. Sold-out switches travel on their own."""
    if await session.get(StockMove, data["id"]):
        return False
    stock = await session.scalar(
        select(StockItem).where(
            StockItem.venue_id == venue_id, StockItem.menu_item_id == data["menu_item_id"]
        )
    )
    if stock is None:
        stock = StockItem(venue_id=venue_id, menu_item_id=data["menu_item_id"], on_hand=0, auto_off=False)
        session.add(stock)
    stock.on_hand += data["change"]
    session.add(
        StockMove(
            id=data["id"],
            venue_id=venue_id,
            menu_item_id=data["menu_item_id"],
            change=data["change"],
            reason=data["reason"],
            order_id=data.get("order_id"),
            by=data.get("by"),
            created_at=_dt(data["created_at"]),
        )
    )
    return True


INGESTERS = {
    "stock.move": ingest_stock_move,
    "order.snapshot": ingest_order,
    "invoice": ingest_invoice,
    "shift": ingest_shift,
    "menu.availability": ingest_availability,
}
