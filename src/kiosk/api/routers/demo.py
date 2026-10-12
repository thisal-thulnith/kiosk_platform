"""The public demo (DEMO_MODE=true, its own server and data): anyone can open every screen of the
demo restaurant with one tap at /try, without a screen code. Never turned on for real restaurants.

Each tap makes a fresh screen (its own key), so several visitors can try the same screen at once.
Old demo screens are turned off when there are too many; the demo data is reset every night.
"""

import time
from collections import defaultdict, deque
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api.deps import Uow
from kiosk.auth.security import new_token, token_digest
from kiosk.config import settings
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import Device, Venue, utcnow
from kiosk.seed import DEMO, PLATFORM

router = APIRouter(prefix="/v1/demo", tags=["demo"])

TABLES = ["T1", "T2", "T3", "T4", "T5", "T6"]
MAX_SCREENS = 80  # demo screens kept on; older ones are turned off
PER_IP = 40  # new screens per visitor address per 10 minutes
STYLES: dict[str, dict[str, Any]] = {
    # A sit-down restaurant: order rounds, the waiter brings food, pay at the end.
    "sit_down": {"dine_in_mode": "tab", "serve_mode": "waiter", "table_access": "open", "release_rule": "B"},
    # Quick service: pay first (QR / card / at the counter), collect at the counter.
    "quick": {
        "dine_in_mode": "pay_first",
        "serve_mode": "self_pickup",
        "table_access": "open",
        "release_rule": "A",
    },
}
NAMES = {
    "cashier": "POS",
    "waiter": "Waiter app",
    "kds": "Kitchen",
    "kiosk": "Kiosk",
    "status": "Status board",
}
_made: dict[str, deque[float]] = defaultdict(deque)


def _limit(request: Request) -> None:
    q = _made[request.client.host if request.client else "?"]
    now = time.monotonic()
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= PER_IP:
        raise AppError("too_many_attempts", "That's a lot of screens. Wait a few minutes and try again", 429)
    q.append(now)


async def _venue(uow: Uow) -> Venue:
    if not settings.demo_mode:
        raise NotFound("Page")
    venue = await uow.session.scalar(select(Venue).where(Venue.code == "DEMO"))
    if venue is None:
        raise AppError("demo_not_ready", "The demo restaurant isn't set up yet (run kiosk seed)", 503)
    return venue


def _style(venue: Venue) -> str:
    return next((k for k, v in STYLES.items() if all(venue.setting(x) == y for x, y in v.items())), "custom")


@router.get("")
async def demo_info(uow: Uow) -> dict[str, Any]:
    """What the /try page shows: the restaurant, its tables, the staff PINs and the logins."""
    venue = await _venue(uow)
    if not (venue.settings or {}).get("demo_ready"):
        venue.settings = {**(venue.settings or {}), **STYLES["sit_down"], "demo_ready": True}
        await uow.commit()
    return {
        "venue": {"code": venue.code.lower(), "name": venue.name},
        "style": _style(venue),
        "tables": TABLES,
        "staff": [{"name": n, "role": r, "pin": p} for n, r, p in DEMO["staff"]],
        "owner": {"email": DEMO["admin_email"], "password": DEMO["admin_password"]},
        "team": PLATFORM,
    }


class ScreenIn(BaseModel):
    type: Literal["cashier", "waiter", "kds", "table", "kiosk", "status"]
    table_ref: str | None = Field(default=None, max_length=10)


@router.post("/screen")
async def demo_screen(body: ScreenIn, request: Request, uow: Uow) -> dict[str, Any]:
    """A new screen of the demo restaurant, signed in: the same answer as /v1/devices/sign-in."""
    venue = await _venue(uow)
    _limit(request)
    if body.type == "table" and body.table_ref not in TABLES:
        raise AppError("table_ref_required", "Choose a table")
    token = new_token()
    device = Device(
        venue_id=venue.id,
        type=body.type,
        name=f"Table {body.table_ref}" if body.type == "table" else f"{NAMES[body.type]} (demo)",
        table_ref=body.table_ref if body.type == "table" else None,
        token_hash=token_digest(token),
        last_seen_at=utcnow(),
        settings={"demo": True},
    )
    uow.session.add(device)
    await uow.session.flush()
    # Keep the demo tidy: only the newest screens stay on.
    on = (
        await uow.session.scalars(
            select(Device)
            .where(Device.venue_id == venue.id, Device.is_active)
            .order_by(Device.created_at.desc())
            .offset(MAX_SCREENS)
        )
    ).all()
    for old in on:
        if (old.settings or {}).get("demo"):
            old.is_active = False
    await uow.commit()
    return {
        "device_token": token,
        "device": {
            "id": device.id,
            "type": device.type,
            "name": device.name,
            "venue_id": venue.id,
            "venue_code": venue.code,
            "station": None,
            "table_ref": device.table_ref,
        },
        "replaced_another_device": False,
    }


class StyleIn(BaseModel):
    style: Literal["sit_down", "quick"]


@router.post("/style")
async def demo_style(body: StyleIn, uow: Uow) -> dict[str, Any]:
    """Switch the demo restaurant between a sit-down restaurant and quick service. Every open
    screen follows at once (venue.settings)."""
    venue = await _venue(uow)
    venue.settings = {**(venue.settings or {}), **STYLES[body.style]}
    uow.emit(
        venue.id,
        "venue.settings",
        {"settings": venue.settings},
        ["menu", "status", "orders", "kds", "service"],
    )
    await uow.commit()
    return {"style": body.style}
