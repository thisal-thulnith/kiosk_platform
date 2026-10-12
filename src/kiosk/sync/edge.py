"""Hub (edge) background worker, every few seconds while the internet works:

  1. pull config when it changed (menu, prices, staff, screens and their key hashes, printers...)
  2. push this hub's outbox (orders, invoices, shifts, stock moves...)
  3. pull the cloud's change feed (payments the bank confirmed at the cloud, backup-mode orders)
     and apply it here, telling this hub's screens live
  4. heartbeat: "I'm alive, this is my address, this is what I've applied"

When the internet is down every step fails quietly and the hub keeps serving its screens; the
outbox simply grows and is sent when the internet is back. Safe to resend: the receiving side
ignores order versions it already has, invoices and stock moves it has seen.
"""

import asyncio
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.config import settings
from kiosk.domain.orders import Status
from kiosk.infra.db import session_factory
from kiosk.infra.lan import lan_url
from kiosk.infra.models import HubStatus, Order, Outbox, Venue, utcnow
from kiosk.realtime.hub import hub
from kiosk.services import payments as pay
from kiosk.services.uow import UnitOfWork
from kiosk.sync.snapshot import INGESTERS, apply_config, ingest_order
from kiosk.sync.state import state

SOFTWARE = "kiosk-hub/0.1.0"
CALLBACKS = {
    "gateway.callback": pay.handle_gateway_callback,
    "terminal.callback": pay.handle_terminal_callback,
}

log = structlog.get_logger()
BATCH = 200


def _headers() -> dict[str, str]:
    return {"X-Venue-Id": settings.venue_id or "", "X-Sync-Key": settings.cloud_sync_key or ""}


async def push_once(client: httpx.AsyncClient) -> int:
    async with session_factory()() as session:
        rows = (
            await session.scalars(
                select(Outbox)
                .where(Outbox.sent_at.is_(None))
                .order_by(Outbox.created_at, Outbox.id)
                .limit(BATCH)
            )
        ).all()
        if not rows:
            state.pending = 0
            return 0
        entries = [{"id": r.id, "kind": r.kind, "payload": r.payload} for r in rows]
        try:
            resp = await client.post("/v1/sync/ingest", json={"entries": entries}, headers=_headers())
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            for r in rows:
                r.attempts += 1
                r.last_error = str(exc)[:500]
            await session.commit()
            raise
        now = utcnow()
        for r in rows:
            r.sent_at = now
        await session.commit()
        state.pending = int(
            await session.scalar(select(func.count()).select_from(Outbox).where(Outbox.sent_at.is_(None)))
            or 0
        )
        state.last_push_at = now
        return len(rows)


async def pull_once(client: httpx.AsyncClient) -> bool:
    async with session_factory()() as session:
        venue = await session.get(Venue, settings.venue_id)
        since = venue.config_version if venue else 0
        resp = await client.get("/v1/sync/config", params={"since": since}, headers=_headers())
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        state.last_pull_at = utcnow()
        if not body.get("changed"):
            return False
        await apply_config(session, body["config"])
        await session.commit()
        log.info("sync.config_applied", version=body["config"]["config_version"])
        return True


async def _local_status(session: AsyncSession) -> HubStatus:
    row: HubStatus | None = await session.get(HubStatus, settings.venue_id)
    if row is None:
        row = HubStatus(venue_id=settings.venue_id, pending=0, info={})
        session.add(row)
    return row


async def _apply_change(entry: dict[str, Any]) -> None:
    """One change from the cloud, in its own transaction, then its live event for this hub's screens."""
    kind, data = entry["kind"], entry["payload"]
    async with session_factory()() as session:
        if kind in CALLBACKS:
            uow = UnitOfWork(session)
            try:
                await CALLBACKS[kind](uow, data)
                await uow.commit()  # publishes order.paid etc. to the screens, prints the receipt
            except Exception:  # noqa: BLE001 - a payment we don't know (yet) must not stop the feed
                log.warning("sync.callback_not_applied", kind=kind)
            return
        if kind == "order.snapshot":
            applied = await ingest_order(session, settings.venue_id or "", data)
            await session.commit()
            if applied:
                snap = {k: v for k, v in data.items() if k != "_event"}
                stations = sorted({i["station"] for i in snap.get("items", [])})
                topics = ["orders", "status", "kds", *(f"kds:{s}" for s in stations)]
                await hub.publish(
                    settings.venue_id or "", data.get("_event") or "order.synced", {"order": snap}, topics
                )
            return
        handler = INGESTERS.get(kind)
        if handler and await handler(session, settings.venue_id or "", data):
            await session.commit()
            if kind == "menu.availability":
                await hub.publish(
                    settings.venue_id or "", "menu.item_availability", data, ["menu", "orders", "kds"]
                )


async def pull_changes(client: httpx.AsyncClient) -> int:
    async with session_factory()() as session:
        after = (await _local_status(session)).cloud_cursor
        await session.commit()
    resp = await client.get("/v1/sync/changes", params={"after": after} if after else {}, headers=_headers())
    resp.raise_for_status()
    body: dict[str, Any] = resp.json()
    for entry in body["entries"]:
        await _apply_change(entry)
    async with session_factory()() as session:
        row = await _local_status(session)
        row.cloud_cursor = body.get("last") or row.cloud_cursor
        await session.commit()
    return len(body["entries"])


async def heartbeat(client: httpx.AsyncClient) -> None:
    async with session_factory()() as session:
        row = await _local_status(session)
        open_orders = await session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.status.in_([Status.PLACED, Status.IN_KITCHEN, Status.READY]))
        )
        body = {
            "lan_url": lan_url(),
            "software": SOFTWARE,
            "pending": state.pending,
            "cloud_cursor": row.cloud_cursor,
            "open_orders": int(open_orders or 0),
        }
        await session.commit()
    resp = await client.post("/v1/sync/heartbeat", json=body, headers=_headers())
    resp.raise_for_status()


async def sync_once(client: httpx.AsyncClient) -> None:
    await pull_once(client)
    while await push_once(client) == BATCH:
        pass
    while await pull_changes(client) == 200:
        pass
    await heartbeat(client)


async def run_forever(stop: asyncio.Event) -> None:
    if not (settings.cloud_url and settings.venue_id and settings.cloud_sync_key):
        log.info("sync.disabled", reason="cloud_url, venue_id and cloud_sync_key are not all set")
        return
    backoff = settings.sync_interval_seconds
    async with httpx.AsyncClient(base_url=settings.cloud_url, timeout=10) as client:
        while not stop.is_set():
            try:
                await sync_once(client)
                if not state.cloud_online:
                    log.info("sync.online")
                state.cloud_online, state.last_error = True, None
                backoff = settings.sync_interval_seconds
            except Exception as exc:  # noqa: BLE001
                if state.cloud_online:
                    log.warning("sync.offline", error=str(exc))
                state.cloud_online, state.last_error = False, str(exc)
                backoff = min(backoff * 2, 60)
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
