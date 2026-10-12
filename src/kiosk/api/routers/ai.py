"""AI mode for screens and the owner. Screens ask what to highlight; the owner sees why."""

from typing import Any, Literal

from fastapi import APIRouter
from sqlalchemy import select

from kiosk.api.deps import Admin, AdminVenue, Ctx, Uow
from kiosk.api.routers.admin_org import bump_config
from kiosk.api.routers.kds import kitchen_load
from kiosk.errors import Conflict, NotFound
from kiosk.infra.models import AiAction, MenuItem, PriceOffer, utcnow
from kiosk.services.ai import compute_policy, offer_dict

router = APIRouter(prefix="/v1", tags=["ai"])


@router.get("/ai/policy")
async def policy(ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """What guest screens should highlight right now. Inactive in Manual mode."""
    result = await compute_policy(uow, ctx.venue, await kitchen_load(uow, ctx.venue))
    result.pop("insights", None)  # insights are for staff and the owner, not guests
    return result


@router.get("/admin/venues/{venue_id}/ai")
async def owner_view(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    """Mode, level, current insights and the latest AI decisions with their reasons."""
    result = await compute_policy(uow, venue, await kitchen_load(uow, venue))
    rows = (
        await uow.session.scalars(
            select(AiAction)
            .where(AiAction.venue_id == venue.id)
            .order_by(AiAction.created_at.desc())
            .limit(20)
        )
    ).all()
    result["log"] = [
        {"kind": r.kind, "reason": r.reason, "data": r.data, "at": r.created_at.isoformat()} for r in rows
    ]
    result["offers"] = await _offers(uow, venue.id)
    return result


async def _offers(uow: Uow, venue_id: str) -> list[dict[str, Any]]:
    offers = (
        await uow.session.scalars(
            select(PriceOffer)
            .where(PriceOffer.venue_id == venue_id)
            .order_by(PriceOffer.created_at.desc())
            .limit(20)
        )
    ).all()
    items = (
        await uow.session.scalars(select(MenuItem).where(MenuItem.id.in_({o.menu_item_id for o in offers})))
    ).all()
    names = {m.id: m.name.get("en", m.id) for m in items}
    prices = {m.id: m.price for m in items}
    return [offer_dict(o, names, prices) for o in offers]


@router.post("/admin/venues/{venue_id}/ai/offers/{offer_id}/{decision}")
async def decide_offer(
    offer_id: str, decision: Literal["approve", "reject"], venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    """The owner approves or rejects an AI deal. Approving an active one again is refused."""
    offer = await uow.session.get(PriceOffer, offer_id)
    if offer is None or offer.venue_id != venue.id:
        raise NotFound("Offer")
    if offer.ends_at <= utcnow():
        raise Conflict("offer_expired", "This deal has already ended")
    if decision == "approve" and offer.status != "proposed":
        raise Conflict("offer_decided", f"This deal is already {offer.status}")
    offer.status = "active" if decision == "approve" else "rejected"
    offer.starts_at = utcnow() if decision == "approve" else offer.starts_at
    offer.decided_by = admin.email
    uow.session.add(
        AiAction(
            venue_id=venue.id,
            kind="offer",
            data={"offer_id": offer.id, "status": offer.status},
            reason=f"{'Approved' if decision == 'approve' else 'Rejected'} by {admin.email}",
        )
    )
    uow.audit(admin.actor(venue.id), f"ai.offer_{decision}", offer.id, discount_bp=offer.discount_bp)
    uow.emit(venue.id, "menu.offers", {"offer_id": offer.id, "status": offer.status}, ["menu"])
    item = await uow.session.get(MenuItem, offer.menu_item_id)
    bump_config(venue)  # approved deals reach the restaurant's hub
    await uow.commit()
    return offer_dict(
        offer,
        {offer.menu_item_id: item.name.get("en", "") if item else ""},
        {offer.menu_item_id: item.price if item else 0},
    )
