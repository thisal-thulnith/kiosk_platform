"""Guest feedback: the table (or kiosk) sends it; waiters and the POS see it live; owners get a report."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from kiosk.api.deps import AdminVenue, Ctx, Uow
from kiosk.errors import Forbidden
from kiosk.infra.models import utcnow
from kiosk.services import feedback as svc
from kiosk.services.menu import local_now

router = APIRouter(prefix="/v1", tags=["feedback"])


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5, description="Stars, 1 to 5")
    tags: list[str] = Field(default_factory=list, max_length=8, description=f"Any of: {', '.join(svc.TAGS)}")
    comment: str | None = Field(default=None, max_length=500)
    order_id: str | None = None


@router.post("/feedback", status_code=201)
async def give_feedback(body: FeedbackIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """After eating. A table sends it for its own table; one per order (sending again changes it)."""
    if ctx.device.type not in ("table", "kiosk", "waiter", "cashier"):
        raise Forbidden("Feedback comes from a table, kiosk or staff screen")
    table = ctx.device.table_ref if ctx.device.type == "table" else None
    f = await svc.give(uow, ctx.venue, ctx.actor, table, body.order_id, body.rating, body.tags, body.comment)
    await uow.commit()
    return svc.feedback_dict(f)


def _staff_screen(ctx: Ctx) -> None:
    if ctx.device.type not in ("waiter", "cashier") and ctx.staff is None:
        raise Forbidden("Feedback is shown on staff screens")


@router.get("/feedback")
async def recent_feedback(ctx: Ctx, uow: Uow) -> list[dict[str, Any]]:
    """The last 12 hours, newest first (staff screens)."""
    _staff_screen(ctx)
    return await svc.recent(uow, ctx.venue)


@router.post("/feedback/{feedback_id}/seen")
async def seen(feedback_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    _staff_screen(ctx)
    f = await svc.mark_seen(uow, ctx.venue, feedback_id, ctx.actor)
    out = svc.feedback_dict(f, await svc.staff_names(uow, ctx.venue))
    await uow.commit()
    return out


@router.get("/admin/venues/{venue_id}/reports/feedback")
async def feedback_report(
    venue: AdminVenue,
    uow: Uow,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> dict[str, Any]:
    today = local_now(venue, utcnow()).date()
    lo, hi = svc.day_range(venue, (from_ or today).isoformat(), (to or today).isoformat())
    return {
        "from": (from_ or today).isoformat(),
        "to": (to or today).isoformat(),
        **await svc.report(uow, venue, lo, hi),
    }
