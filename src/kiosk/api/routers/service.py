"""Guest calls for staff: "Call waiter" and "Request bill" on table screens, "Help" on kiosks.

Requests appear live on POS and waiter screens. "Coming" names who goes: on a waiter's phone it is
that waiter; on the POS the cashier picks the waiter. Every screen, and the guest's table, then shows
"Priya is coming". "Done" closes it. Who answered and how fast is kept for the owner's reports.
"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from kiosk.api.deps import Ctx, Uow
from kiosk.errors import Conflict, Forbidden, NotFound
from kiosk.infra.models import ServiceRequest, Staff, utcnow

router = APIRouter(prefix="/v1/service-requests", tags=["service requests"])

GUEST_DEVICES = {"table": {"call_waiter", "request_bill"}, "kiosk": {"help"}}
STAFF_DEVICES = {"cashier", "waiter"}


def request_dict(r: ServiceRequest, names: dict[str, str] | None = None) -> dict[str, Any]:
    who = r.acknowledged_by
    return {
        "id": r.id,
        "kind": r.kind,
        "where": r.where,
        "table_ref": r.table_ref,
        "device_id": r.device_id,
        "order_id": r.order_id,
        "pay_with": r.pay_with,
        "status": r.status,
        "created_at": r.created_at.isoformat(),
        "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
        # Who is coming (shown on every staff screen and to the guest).
        "coming": {"staff_id": who, "name": (names or {}).get(who or "")} if who else None,
        "done_at": r.done_at.isoformat() if r.done_at else None,
    }


class RequestIn(BaseModel):
    kind: Literal["call_waiter", "request_bill", "help"]
    order_id: str | None = None
    # Asking for the bill: how the guests will pay, so the waiter brings the right thing.
    pay_with: Literal["cash", "card", "qr"] | None = None


@router.post("", status_code=201)
async def create(body: RequestIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    allowed = GUEST_DEVICES.get(ctx.device.type, set())
    if body.kind not in allowed:
        raise Forbidden(f"A {ctx.device.type} screen cannot send '{body.kind}'")
    # Pressing the button twice does not page staff twice.
    existing = await uow.session.scalar(
        select(ServiceRequest).where(
            ServiceRequest.device_id == ctx.device.id,
            ServiceRequest.kind == body.kind,
            ServiceRequest.status != "done",
        )
    )
    if existing:
        if body.pay_with and existing.pay_with != body.pay_with:  # changed their mind: cash -> card
            existing.pay_with = body.pay_with
            uow.emit(
                ctx.venue.id, "service.requested", {"request": request_dict(existing)}, ["orders", "service"]
            )
            await uow.commit()
        return request_dict(existing)
    where = f"Table {ctx.device.table_ref}" if ctx.device.type == "table" else ctx.device.name
    req = ServiceRequest(
        venue_id=ctx.venue.id,
        device_id=ctx.device.id,
        kind=body.kind,
        table_ref=ctx.device.table_ref,
        where=where,
        order_id=body.order_id,
        pay_with=body.pay_with if body.kind == "request_bill" else None,
    )
    uow.session.add(req)
    await uow.session.flush()
    uow.emit(ctx.venue.id, "service.requested", {"request": request_dict(req)}, ["orders", "service"])
    await uow.commit()
    return request_dict(req)


@router.get("")
async def list_requests(ctx: Ctx, uow: Uow, mine: bool = False) -> list[dict[str, Any]]:
    """Staff screens: all open requests. Guest screens: their own (mine=true)."""
    stmt = select(ServiceRequest).where(
        ServiceRequest.venue_id == ctx.venue.id, ServiceRequest.status != "done"
    )
    if mine or ctx.device.type not in STAFF_DEVICES:
        stmt = stmt.where(ServiceRequest.device_id == ctx.device.id)
    rows = (await uow.session.scalars(stmt.order_by(ServiceRequest.created_at))).all()
    names = await _names(uow, ctx.venue.id)
    return [request_dict(r, names) for r in rows]


async def _names(uow: Uow, venue_id: str) -> dict[str, str]:
    rows = await uow.session.execute(select(Staff.id, Staff.name).where(Staff.venue_id == venue_id))
    return {str(k): str(v) for k, v in rows.all()}


async def _staff_update(
    ctx: Ctx, uow: Uow, request_id: str, status: str, staff_id: str | None = None
) -> dict[str, Any]:
    if ctx.device.type not in STAFF_DEVICES:
        raise Forbidden("Only cashier or waiter screens can answer requests")
    req = await uow.session.get(ServiceRequest, request_id)
    if req is None or req.venue_id != ctx.venue.id:
        raise NotFound("Service request")
    if req.status == "done":
        raise Conflict("request_done", "This request is already done")
    now = utcnow()
    names = await _names(uow, ctx.venue.id)
    if staff_id is not None and staff_id not in names:
        raise NotFound("Staff member")
    if status == "acknowledged":
        # Coming: the chosen waiter (POS), or whoever pressed it. Pressing again re-assigns.
        req.status = "acknowledged"
        req.acknowledged_at = req.acknowledged_at or now
        req.acknowledged_by = staff_id or (ctx.staff.id if ctx.staff else req.acknowledged_by)
    elif status == "done":
        req.status, req.done_at = "done", now
        req.acknowledged_at = req.acknowledged_at or now
    out = request_dict(req, names)
    uow.emit(ctx.venue.id, f"service.{status}", {"request": out}, ["orders", "service", "status"])
    await uow.commit()
    return out


class AckIn(BaseModel):
    staff_id: str | None = None  # the waiter who goes (POS); empty = the logged-in staff member


@router.post("/{request_id}/ack")
async def acknowledge(request_id: str, ctx: Ctx, uow: Uow, body: AckIn | None = None) -> dict[str, Any]:
    return await _staff_update(ctx, uow, request_id, "acknowledged", body.staff_id if body else None)


@router.post("/{request_id}/done")
async def done(request_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    return await _staff_update(ctx, uow, request_id, "done")
