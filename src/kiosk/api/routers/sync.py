from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel

from kiosk.api.deps import AdminVenue, Installer, Uow
from kiosk.auth.security import new_token, token_digest
from kiosk.config import settings
from kiosk.errors import AppError, Unauthorized
from kiosk.infra.models import Venue
from kiosk.services import hybrid
from kiosk.sync.snapshot import INGESTERS, build_config
from kiosk.sync.state import state

router = APIRouter(prefix="/v1", tags=["sync"])


async def _venue(uow: Uow, venue_id: str | None, key: str | None) -> Venue:
    if not settings.app_mode == "cloud":
        raise AppError("wrong_mode", "Sync endpoints run on the cloud server", 404)
    venue = await uow.session.get(Venue, venue_id) if venue_id else None
    if venue is None or not key or venue.sync_key_hash != token_digest(key):
        raise Unauthorized("Bad venue sync key")
    return venue


class Entry(BaseModel):
    id: str
    kind: str
    payload: dict[str, Any]


class IngestIn(BaseModel):
    entries: list[Entry]


@router.post("/sync/ingest")
async def ingest(
    body: IngestIn,
    uow: Uow,
    x_venue_id: Annotated[str | None, Header()] = None,
    x_sync_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Receive outbox entries from an edge server. Idempotent."""
    venue = await _venue(uow, x_venue_id, x_sync_key)
    applied = 0
    for e in body.entries:
        handler = INGESTERS.get(e.kind)
        if handler and await handler(uow.session, venue.id, e.payload):
            applied += 1
    await uow.commit()
    return {"received": len(body.entries), "applied": applied}


@router.get("/sync/config")
async def config(
    uow: Uow,
    since: int = 0,
    x_venue_id: Annotated[str | None, Header()] = None,
    x_sync_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    venue = await _venue(uow, x_venue_id, x_sync_key)
    if venue.config_version <= since:
        return {"changed": False, "config_version": venue.config_version}
    return {"changed": True, "config": await build_config(uow.session, venue)}


class RegisterIn(BaseModel):
    code: str
    lan_url: str | None = None


@router.post("/sync/register")
async def register_hub(body: RegisterIn, uow: Uow) -> dict[str, Any]:
    """`kiosk hub-setup` on the hub box: trade the one-time code from the Setup console for the
    venue's sync key. A new hub replaces the old one (the old key stops working)."""
    if settings.app_mode != "cloud":
        raise AppError("wrong_mode", "Hubs register with the cloud server", 404)
    result = await hybrid.register(uow, body.code, body.lan_url)
    await uow.commit()
    return result


class HeartbeatIn(BaseModel):
    lan_url: str | None = None
    software: str | None = None
    pending: int = 0
    cloud_cursor: str | None = None
    open_orders: int | None = None


@router.post("/sync/heartbeat")
async def hub_heartbeat(
    body: HeartbeatIn,
    uow: Uow,
    x_venue_id: Annotated[str | None, Header()] = None,
    x_sync_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    venue = await _venue(uow, x_venue_id, x_sync_key)
    result = await hybrid.heartbeat(uow, venue, body.model_dump())
    await uow.commit()
    return result


@router.get("/sync/changes")
async def cloud_changes(
    uow: Uow,
    after: str | None = None,
    x_venue_id: Annotated[str | None, Header()] = None,
    x_sync_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """What happened at the cloud for this venue (payments the bank confirmed, backup-mode orders)."""
    venue = await _venue(uow, x_venue_id, x_sync_key)
    return await hybrid.changes(uow, venue.id, after)


@router.get("/admin/venues/{venue_id}/network", tags=["admin"])
async def network_status(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    return await hybrid.network(uow, venue)


class NetworkIn(BaseModel):
    mode: str


@router.put("/admin/venues/{venue_id}/network", tags=["admin"])
async def set_network(body: NetworkIn, venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    if body.mode not in ("cloud", "hybrid"):
        raise AppError("bad_setting", "Network mode is cloud or hybrid")
    venue.settings = {**(venue.settings or {}), "network_mode": body.mode}
    venue.config_version += 1
    uow.audit(admin.actor(venue.id), "network.mode", venue.id, mode=body.mode)
    await uow.commit()
    return await hybrid.network(uow, venue)


@router.post("/admin/venues/{venue_id}/hub/setup-code", tags=["admin"])
async def hub_setup_code(venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    result = await hybrid.new_setup_code(uow, venue, admin.actor(venue.id))
    await uow.commit()
    return {**result, "cloud_url": settings.public_url}


@router.post("/admin/venues/{venue_id}/sync-key", tags=["admin"])
async def rotate_sync_key(venue: AdminVenue, admin: Installer, uow: Uow) -> dict[str, Any]:
    """Create a new key for this venue's edge server. Shown once; the old key stops working."""
    key = new_token()
    venue.sync_key_hash = token_digest(key)
    uow.audit(admin.actor(venue.id), "sync.key_rotated", venue.id)
    await uow.commit()
    return {"venue_id": venue.id, "sync_key": key}


@router.get("/sync/status")
async def status() -> dict[str, Any]:
    return {
        "mode": settings.app_mode,
        "cloud_online": state.cloud_online,
        "pending": state.pending,
        "last_push_at": state.last_push_at.isoformat() if state.last_push_at else None,
        "last_pull_at": state.last_pull_at.isoformat() if state.last_pull_at else None,
        "last_error": state.last_error,
    }
