"""Hybrid venues: the restaurant's hub and the cloud, and which one is in charge.

A "cloud" venue: every screen talks to the cloud.

A "hybrid" venue has a hub in the restaurant (the same software in edge mode):
  - While the hub is alive (heartbeat within HUB_TIMEOUT), only the hub changes orders. The cloud
    answers screens with "use_hub" and forwards payment confirmations from the bank to the hub.
    So there is only ever one writer, and nothing to merge.
  - If the hub is down, screens reach the cloud directly and the cloud takes over ("backup mode"),
    giving order numbers from 500 up and invoice numbers from a C series, so nothing collides.
  - When the hub comes back it first applies everything the cloud did (the cloud's change feed),
    and only then is it in charge again.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from kiosk.auth.security import new_token, token_digest
from kiosk.config import settings
from kiosk.errors import AppError
from kiosk.infra.models import HubStatus, Outbox, Venue, utcnow
from kiosk.services.uow import Actor, UnitOfWork

BACKUP_TOKEN_OFFSET = 500
SETUP_CODE_MINUTES = 30
# The cloud's change feed for a hub: what the hub must apply (never echoed back).
FEED_KINDS = (
    "order.snapshot",
    "invoice",
    "shift",
    "menu.availability",
    "stock.move",
    "gateway.callback",
    "terminal.callback",
)


def is_hybrid(venue: Venue) -> bool:
    return bool(venue.setting("network_mode") == "hybrid")


def cloud_backup(venue: Venue) -> bool:
    """This server is the cloud standing in for a hybrid venue's hub (order and invoice series)."""
    return settings.app_mode == "cloud" and is_hybrid(venue)


async def status_row(uow: UnitOfWork, venue_id: str) -> HubStatus | None:
    return await uow.session.get(HubStatus, venue_id)


def alive(row: HubStatus | None) -> bool:
    """The hub is in charge: heard from recently, and not still catching up after a takeover."""
    if row is None or row.last_seen_at is None or row.registered_at is None:
        return False
    fresh = utcnow() - row.last_seen_at < timedelta(seconds=settings.hub_timeout_seconds)
    return fresh and not (row.info or {}).get("takeover")


async def hub_in_charge(uow: UnitOfWork, venue: Venue) -> bool:
    """On the cloud: a hybrid venue whose hub is alive. Its screens must use the hub."""
    if settings.app_mode != "cloud" or not is_hybrid(venue):
        return False
    return alive(await status_row(uow, venue.id))


async def note_takeover(uow: UnitOfWork, venue: Venue) -> None:
    """The cloud accepted a screen's change while the hub was down: the hub must catch up first."""
    row = await status_row(uow, venue.id)
    if row is not None and row.registered_at is not None and not (row.info or {}).get("takeover"):
        row.info = {**(row.info or {}), "takeover": utcnow().isoformat()}


# ------------------------------------------------------------------ hub registration (cloud)


async def new_setup_code(uow: UnitOfWork, venue: Venue, actor: Actor) -> dict[str, Any]:
    """An 8-character one-time code the installer types into `kiosk hub-setup` on the hub box."""
    code = new_token()[:8].upper().replace("-", "X").replace("_", "Y")
    row = await status_row(uow, venue.id)
    if row is None:
        row = HubStatus(venue_id=venue.id, pending=0, info={})
        uow.session.add(row)
    row.setup_code_hash = token_digest(code)
    row.setup_expires_at = utcnow() + timedelta(minutes=SETUP_CODE_MINUTES)
    uow.audit(actor, "hub.setup_code", venue.id)
    return {"code": code, "expires_at": row.setup_expires_at.isoformat()}


async def register(uow: UnitOfWork, code: str, lan_url: str | None) -> dict[str, Any]:
    row = await uow.session.scalar(
        select(HubStatus).where(HubStatus.setup_code_hash == token_digest(code.strip().upper()))
    )
    if row is None or row.setup_expires_at is None or row.setup_expires_at < utcnow():
        raise AppError(
            "bad_code", "Hub setup code is wrong or expired. Make a new one in the Setup console", 401
        )
    venue = await uow.session.get(Venue, row.venue_id)
    assert venue is not None
    key = new_token()
    venue.sync_key_hash = token_digest(key)  # a new hub replaces the old one
    venue.settings = {**(venue.settings or {}), "network_mode": "hybrid"}
    venue.config_version += 1
    row.setup_code_hash, row.setup_expires_at = None, None
    row.registered_at, row.lan_url, row.info = utcnow(), lan_url, {}
    uow.audit(Actor(venue_id=venue.id), "hub.registered", venue.id, lan_url=lan_url)
    return {"venue_id": venue.id, "venue_name": venue.name, "sync_key": key}


async def latest_change(uow: UnitOfWork, venue_id: str) -> str | None:
    return await uow.session.scalar(
        select(func.max(Outbox.id)).where(Outbox.venue_id == venue_id, Outbox.kind.in_(FEED_KINDS))
    )


async def heartbeat(uow: UnitOfWork, venue: Venue, body: dict[str, Any]) -> dict[str, Any]:
    row = await status_row(uow, venue.id)
    if row is None:
        row = HubStatus(venue_id=venue.id, pending=0, info={}, registered_at=utcnow())
        uow.session.add(row)
    row.last_seen_at = utcnow()
    row.lan_url = body.get("lan_url") or row.lan_url
    row.software = body.get("software")
    row.pending = int(body.get("pending") or 0)
    row.cloud_cursor = body.get("cloud_cursor") or row.cloud_cursor
    info = dict(row.info or {})
    if info.get("takeover"):
        latest = await latest_change(uow, venue.id)
        if latest is None or (row.cloud_cursor or "") >= latest:
            info.pop("takeover")  # caught up: the hub is in charge again
            uow.audit(Actor(venue_id=venue.id), "hub.back_in_charge", venue.id)
    info["open_orders"] = body.get("open_orders")
    row.info = info
    return {"ok": True, "in_charge": "takeover" not in info, "server_time": utcnow().isoformat()}


async def changes(uow: UnitOfWork, venue_id: str, after: str | None, limit: int = 200) -> dict[str, Any]:
    q = select(Outbox).where(Outbox.venue_id == venue_id, Outbox.kind.in_(FEED_KINDS))
    if after:
        q = q.where(Outbox.id > after)
    rows = (await uow.session.scalars(q.order_by(Outbox.id).limit(limit))).all()
    return {
        "entries": [{"id": r.id, "kind": r.kind, "payload": r.payload} for r in rows],
        "last": rows[-1].id if rows else after,
        "more": len(rows) == limit,
    }


async def network(uow: UnitOfWork, venue: Venue) -> dict[str, Any]:
    row = await status_row(uow, venue.id)
    return {
        "mode": venue.setting("network_mode"),
        "hub": None
        if row is None or row.registered_at is None
        else {
            "alive": alive(row),
            "catching_up": bool((row.info or {}).get("takeover")),
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "lan_url": row.lan_url,
            "software": row.software,
            "pending": row.pending,
            "open_orders": (row.info or {}).get("open_orders"),
            "registered_at": row.registered_at.isoformat(),
        },
        "setup_code_active": bool(row and row.setup_expires_at and row.setup_expires_at > utcnow()),
        "in_charge": "hub" if alive(row) and is_hybrid(venue) else "cloud",
    }
