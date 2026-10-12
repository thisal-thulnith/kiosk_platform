from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from kiosk.api.deps import Ctx, DeviceCtx, Uow, require_device
from kiosk.domain.orders import ItemStatus, Status
from kiosk.errors import Forbidden, NotFound
from kiosk.infra.models import MenuItem, Order, utcnow
from kiosk.services.menu import effective_menu
from kiosk.services.serializers import menu_item_dict

router = APIRouter(prefix="/v1/menu", tags=["menu"])


@router.get("")
async def get_menu(ctx: Ctx, uow: Uow) -> dict[str, Any]:
    """What this screen shows now. A screen can be limited to some categories (e.g. a drinks kiosk)."""
    only = ((ctx.device.settings or {}).get("menu") or {}).get("categories") or None
    return await effective_menu(uow.session, ctx.venue, utcnow(), only)


class Availability(BaseModel):
    is_available: bool


async def _orders_waiting_for(uow: Uow, venue_id: str, item_id: str) -> list[dict[str, Any]]:
    rows = (
        await uow.session.scalars(
            select(Order).where(
                Order.venue_id == venue_id, Order.status.in_([Status.PLACED, Status.IN_KITCHEN])
            )
        )
    ).all()
    return [
        {"order_id": o.id, "token": o.token, "table_ref": o.table_ref}
        for o in rows
        if any(
            i.menu_item_id == item_id and i.kds_status in (ItemStatus.QUEUED, ItemStatus.IN_PROGRESS)
            for i in o.items
        )
    ]


@router.put("/items/{item_id}/availability")
async def set_availability(
    item_id: str,
    body: Availability,
    ctx: Annotated[DeviceCtx, Depends(require_device("kds", "cashier", "waiter"))],
    uow: Uow,
) -> dict[str, Any]:
    """The "86" switch: sold out disappears from every screen at once."""
    if ctx.device.type != "kds" and ctx.staff is None:
        raise Forbidden("Staff PIN login required")
    item = await uow.session.get(MenuItem, item_id)
    if item is None or item.venue_id != ctx.venue.id:
        raise NotFound("Menu item")
    item.is_available = body.is_available
    item.availability_changed_at = utcnow()
    uow.audit(ctx.actor, "menu.availability", item.id, is_available=body.is_available)
    uow.emit(
        ctx.venue.id,
        "menu.item_availability",
        {"item_id": item.id, "is_available": body.is_available, "name": item.name},
        ["menu", "orders", "kds"],
    )
    uow.outbox(ctx.venue.id, "menu.availability", {"item_id": item.id, "is_available": body.is_available})
    if not body.is_available:
        # Orders already placed that still need this item: tell staff so they can talk to the guest.
        affected = await _orders_waiting_for(uow, ctx.venue.id, item.id)
        if affected:
            uow.emit(
                ctx.venue.id,
                "menu.sold_out_alert",
                {"item_id": item.id, "name": item.name, "orders": affected},
                ["orders", "kds"],
            )
    await uow.commit()
    return menu_item_dict(item)
