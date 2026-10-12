"""Payment ledger for staff screens (POS, waiter) and the owner (with a CSV for the accountant)."""

import csv
import io
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from kiosk.api.deps import AdminVenue, Ctx, Uow
from kiosk.errors import Forbidden
from kiosk.infra.models import utcnow
from kiosk.services import ledger as svc
from kiosk.services.menu import local_now

router = APIRouter(prefix="/v1", tags=["payments ledger"])


@router.get("/payments")
async def staff_ledger(
    ctx: Ctx, uow: Uow, day: str | None = None, method: str | None = None, mine: bool = False
) -> dict[str, Any]:
    """Today's payments (or a day). A waiter sees their own; the POS and managers see all."""
    if ctx.device.type not in ("cashier", "waiter") or ctx.staff is None:
        raise Forbidden("Staff PIN login required")
    day = day or local_now(ctx.venue, utcnow()).date().isoformat()
    only_me = mine or (ctx.device.type == "waiter" and ctx.staff.role not in ("manager", "owner"))
    return await svc.ledger(uow, ctx.venue, day, method, ctx.staff.id if only_me else None)


@router.get("/admin/venues/{venue_id}/reports/payments")
async def owner_ledger(
    venue: AdminVenue, uow: Uow, day: str | None = None, method: str | None = None
) -> dict[str, Any]:
    day = day or local_now(venue, utcnow()).date().isoformat()
    return await svc.ledger(uow, venue, day, method)


@router.get("/admin/venues/{venue_id}/reports/payments.csv")
async def owner_ledger_csv(venue: AdminVenue, uow: Uow, day: str | None = None) -> Response:
    day = day or local_now(venue, utcnow()).date().isoformat()
    data = await svc.ledger(uow, venue, day, limit=10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = [
        "at",
        "ref",
        "kind",
        "status",
        "method",
        "amount",
        "tendered",
        "change_given",
        "token",
        "table",
        "channel",
        "collected_by",
        "device",
        "outside_ref",
        "invoice",
        "reason",
    ]
    w.writerow(cols)
    for x in reversed(data["lines"]):
        w.writerow(
            [
                f"{x[c] / 100:.2f}"
                if c in ("amount", "tendered", "change_given") and x[c] is not None
                else x[c]
                for c in cols
            ]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payments-{venue.code}-{day}.csv"'},
    )
