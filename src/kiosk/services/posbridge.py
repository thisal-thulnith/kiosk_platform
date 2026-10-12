"""Connecting the restaurant's own POS (R-BRIDGE): the kiosks, tables and kitchen are ours, the till
and the accounts stay in their POS.

  push  every order event the POS asked for is POSTed to its URL as JSON, signed:
          X-Kiosk-Event: order.paid
          X-Kiosk-Signature: hex HMAC-SHA256 of the raw body with the shared secret
          X-Kiosk-Delivery: delivery id (the POS ignores ones it has seen)
        Queued first, retried with backoff until the POS answers 2xx.
  pull  the POS calls /v1/pos/... with its key (X-Pos-Key):
          GET  /v1/pos/orders?since=      orders changed since a time
          POST /v1/pos/orders/{id}/paid   the guest paid at the POS: kitchen starts, receipt, points
          GET  /v1/pos/menu               our menu with PLU codes
          PUT  /v1/pos/menu               their menu (PLU, name, price, category, available) -> ours
"""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from kiosk.auth.security import new_token, token_digest
from kiosk.domain.modules import has_module
from kiosk.errors import AppError
from kiosk.infra import secrets
from kiosk.infra.db import session_factory
from kiosk.infra.models import MenuCategory, MenuItem, Order, PosDelivery, PosLink, Venue, utcnow
from kiosk.services.uow import Actor, UnitOfWork

log = structlog.get_logger()
EVENTS = (
    "order.created",
    "order.round_added",
    "order.paid",
    "order.released",
    "order.ready",
    "order.completed",
    "order.cancelled",
    "order.expired",
    "order.voided",
)
DEFAULT_EVENTS = ["order.created", "order.round_added", "order.paid", "order.cancelled", "order.voided"]
MAX_ATTEMPTS = 8
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests put a fake POS here


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def link_for(uow: UnitOfWork, venue_id: str) -> PosLink | None:
    return await uow.session.get(PosLink, venue_id)


def pos_order(order: Order, codes: dict[str, str | None]) -> dict[str, Any]:
    """The order as a POS wants it: lines with PLU codes, money in LKR cents."""
    return {
        "id": order.id,
        "token": order.token,
        "channel": order.channel,
        "table": order.table_ref,
        "status": order.status,
        "payment_status": order.payment_status,
        "is_tab": order.is_tab,
        "subtotal": order.subtotal,
        "discount_total": order.discount_total,
        "tax_lines": order.tax_lines,
        "total": order.total,
        "paid_total": order.paid_total,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "lines": [
            {
                "position": i.position,
                "plu": codes.get(i.menu_item_id),
                "menu_item_id": i.menu_item_id,
                "name": i.name.get("en"),
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "line_total": i.line_total,
                "modifiers": [m["name"].get("en") for m in i.modifiers],
                "notes": i.notes,
                "part_of_combo": i.parent_position,
                "status": i.kds_status,
            }
            for i in order.items
        ],
    }


async def _codes(uow_session: Any, order: Order) -> dict[str, str | None]:
    ids = {i.menu_item_id for i in order.items}
    rows = await uow_session.execute(select(MenuItem.id, MenuItem.external_code).where(MenuItem.id.in_(ids)))
    return dict(rows.all())


async def on_event(uow: UnitOfWork, order: Order, event: str) -> None:
    """Called for every order change; queues the ones the POS subscribed to."""
    if event not in EVENTS:
        return
    link = await link_for(uow, order.venue_id)
    if link is None or not link.is_active or not link.url or event not in (link.events or []):
        return
    venue = await uow.session.get(Venue, order.venue_id)
    if venue is None or not has_module(venue.plan, "R-BRIDGE"):
        return
    payload = {
        "event": event,
        "venue": venue.code,
        "order": pos_order(order, await _codes(uow.session, order)),
    }
    d = PosDelivery(
        venue_id=venue.id, event=event, order_id=order.id, payload=payload, status="queued", attempts=0
    )
    uow.session.add(d)
    await uow.session.flush()
    delivery_id = d.id
    uow.after_commit.append(lambda: deliver(delivery_id))


async def deliver(delivery_id: str) -> None:
    async with session_factory()() as session:
        d = await session.get(PosDelivery, delivery_id)
        if d is None or d.status == "sent":
            return
        link = await session.get(PosLink, d.venue_id)
        if link is None or not link.url:
            d.status, d.error = "failed", "POS not connected"
            await session.commit()
            return
        secret = secrets.decrypt(link.secret_enc) if link.secret_enc else ""
        body = json.dumps({**d.payload, "delivery_id": d.id}, separators=(",", ":")).encode()
        d.attempts += 1
        try:
            async with httpx.AsyncClient(timeout=8, transport=TRANSPORT) as client:
                r = await client.post(
                    link.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Kiosk-Event": d.event,
                        "X-Kiosk-Delivery": d.id,
                        "X-Kiosk-Signature": sign(body, secret or ""),
                    },
                )
            d.response_code = r.status_code
            ok = 200 <= r.status_code < 300
            d.error = None if ok else r.text[:300]
        except httpx.HTTPError as exc:
            ok, d.error = False, str(exc)[:300]
        now = utcnow()
        if ok:
            d.status, link.last_ok_at, link.last_error = "sent", now, None
        else:
            link.last_error = d.error
            d.status = "failed" if d.attempts >= MAX_ATTEMPTS else "queued"
            d.next_try_at = now + timedelta(seconds=min(30 * 2 ** (d.attempts - 1), 3600))
        await session.commit()


async def retry_due() -> int:
    async with session_factory()() as session:
        now = utcnow()
        ids = (
            await session.scalars(
                select(PosDelivery.id)
                .where(
                    PosDelivery.status == "queued", PosDelivery.attempts > 0, PosDelivery.next_try_at <= now
                )
                .order_by(PosDelivery.created_at)
                .limit(50)
            )
        ).all()
    for i in ids:
        await deliver(i)
    return len(ids)


# ------------------------------------------------------------------ setup (installer)


def link_dict(link: PosLink | None) -> dict[str, Any]:
    if link is None:
        return {"connected": False, "events": DEFAULT_EVENTS, "all_events": list(EVENTS)}
    return {
        "connected": True,
        "pos_name": link.pos_name,
        "url": link.url,
        "has_secret": bool(link.secret_enc),
        "has_key": bool(link.key_digest),
        "events": link.events,
        "all_events": list(EVENTS),
        "menu_from_pos": link.menu_from_pos,
        "is_active": link.is_active,
        "last_ok_at": link.last_ok_at.isoformat() if link.last_ok_at else None,
        "last_error": link.last_error,
    }


async def save_link(uow: UnitOfWork, venue: Venue, actor: Actor, data: dict[str, Any]) -> PosLink:
    link = await link_for(uow, venue.id)
    if link is None:
        link = PosLink(venue_id=venue.id, events=list(DEFAULT_EVENTS), is_active=True, menu_from_pos=False)
        uow.session.add(link)
    bad = set(data.get("events") or []) - set(EVENTS)
    if bad:
        raise AppError("bad_event", f"Unknown events: {', '.join(sorted(bad))}")
    url = data.get("url")
    if url and not url.startswith(("https://", "http://")):
        raise AppError("bad_url", "The POS address must start with https://")
    for k in ("pos_name", "url", "menu_from_pos", "is_active"):
        if data.get(k) is not None:
            setattr(link, k, data[k])
    if data.get("events") is not None:
        link.events = list(dict.fromkeys(data["events"]))
    if data.get("secret"):
        link.secret_enc = secrets.encrypt(data["secret"])
    uow.audit(actor, "pos.link_saved", venue.id, pos=link.pos_name, url=link.url)
    return link


async def new_key(uow: UnitOfWork, venue: Venue, actor: Actor) -> str:
    link = await link_for(uow, venue.id) or await save_link(uow, venue, actor, {})
    key = f"pos_{new_token()}"
    link.key_digest = token_digest(key)
    uow.audit(actor, "pos.key_created", venue.id)
    return key


async def venue_for_key(uow: UnitOfWork, key: str | None) -> Venue:
    if not key:
        raise AppError("unauthorized", "POS key required (X-Pos-Key)", 401)
    link = await uow.session.scalar(select(PosLink).where(PosLink.key_digest == token_digest(key)))
    if link is None or not link.is_active:
        raise AppError("unauthorized", "Unknown or disabled POS key", 401)
    venue = await uow.session.get(Venue, link.venue_id)
    assert venue is not None
    return venue


# ------------------------------------------------------------------ menu from the POS


async def import_menu(
    uow: UnitOfWork, venue: Venue, items: list[dict[str, Any]], actor: Actor
) -> dict[str, int]:
    """Their menu into ours, matched by PLU. New items are added; prices, names and availability
    follow the POS. Photos, languages, stations and add-ons stay ours to edit."""
    cats = {
        c.name.get("en", "").lower(): c
        for c in (
            await uow.session.scalars(select(MenuCategory).where(MenuCategory.venue_id == venue.id))
        ).all()
    }
    existing = {
        m.external_code: m
        for m in (
            await uow.session.scalars(
                select(MenuItem).where(MenuItem.venue_id == venue.id, MenuItem.external_code.is_not(None))
            )
        ).all()
    }
    added = updated = 0
    for row in items:
        plu = str(row.get("plu") or "").strip()
        name = str(row.get("name") or "").strip()
        if not plu or not name or not isinstance(row.get("price"), int) or row["price"] < 0:
            raise AppError("bad_menu_row", f"Each item needs plu, name and price in cents: {row}")
        cat_name = str(row.get("category") or "Menu").strip()
        cat = cats.get(cat_name.lower())
        if cat is None:
            cat = MenuCategory(
                venue_id=venue.id, name={"en": cat_name}, sort=len(cats), is_active=True, windows=[]
            )
            uow.session.add(cat)
            await uow.session.flush()
            cats[cat_name.lower()] = cat
        item = existing.get(plu)
        if item is None:
            item = MenuItem(
                venue_id=venue.id,
                category_id=cat.id,
                name={"en": name},
                price=row["price"],
                external_code=plu,
                station=str(row.get("station") or "kitchen"),
                is_active=True,
                is_available=bool(row.get("available", True)),
            )
            uow.session.add(item)
            existing[plu] = item
            added += 1
        else:
            item.name = {**(item.name or {}), "en": name}
            item.price = row["price"]
            item.category_id = cat.id
            if "available" in row:
                item.is_available = bool(row["available"])
            updated += 1
    venue.config_version += 1
    uow.audit(actor, "pos.menu_import", venue.id, added=added, updated=updated)
    uow.emit(venue.id, "menu.updated", {"by": "pos"}, ["menu", "orders", "kds"])
    return {"added": added, "updated": updated}
