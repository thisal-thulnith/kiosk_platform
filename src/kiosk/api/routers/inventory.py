"""Stock (R-INV): the owner sets what is tracked; kitchen and cashier log deliveries and waste."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from kiosk.api.deps import Admin, AdminVenue, DeviceCtx, Uow, require_device
from kiosk.api.routers.admin_org import bump_config
from kiosk.errors import Forbidden
from kiosk.infra.models import MenuItem
from kiosk.services import inventory
from kiosk.services.plans import require_module

router = APIRouter(prefix="/v1", tags=["inventory"])

Staff = Annotated[DeviceCtx, Depends(require_device("kds", "cashier", "waiter"))]


class StockIn(BaseModel):
    on_hand: int | None = Field(None, ge=0, le=100_000)
    low_at: int | None = Field(None, ge=0, le=100_000)
    auto_86: bool | None = None
    perishable_until: datetime | None = None
    clear_perishable: bool = False


class MoveIn(BaseModel):
    kind: Literal["delivery", "count", "waste"]
    quantity: int = Field(ge=0, le=100_000)


async def _one(uow: Uow, stock: Any) -> dict[str, Any]:
    await uow.session.flush()
    result = inventory.stock_dict(stock, await uow.session.get(MenuItem, stock.menu_item_id))
    await uow.commit()
    return result


@router.get("/admin/venues/{venue_id}/stock")
async def owner_stock(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    require_module(venue, "R-INV")
    return await inventory.overview(uow, venue)


@router.put("/admin/venues/{venue_id}/stock/{menu_item_id}")
async def set_stock(
    menu_item_id: str, body: StockIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    require_module(venue, "R-INV")
    stock = await inventory.track(uow, venue, menu_item_id, admin.actor(venue.id), **body.model_dump())
    bump_config(venue)  # the restaurant's hub picks up the stock settings
    return await _one(uow, stock)


@router.delete("/admin/venues/{venue_id}/stock/{menu_item_id}")
async def stop_tracking(menu_item_id: str, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    """Unlimited again. An item switched off by stock is switched back on."""
    require_module(venue, "R-INV")
    stock = await inventory.get(uow, venue, menu_item_id)
    item = await uow.session.get(MenuItem, menu_item_id)
    if stock.auto_off and item is not None and not item.is_available:
        item.is_available = True
        uow.emit(
            venue.id,
            "menu.item_availability",
            {"item_id": item.id, "is_available": True, "name": item.name, "by": "stock"},
            ["menu", "orders", "kds"],
        )
    await uow.session.delete(stock)
    uow.audit(admin.actor(venue.id), "stock.untrack", menu_item_id)
    bump_config(venue)
    await uow.commit()
    return {"menu_item_id": menu_item_id, "tracked": False}


@router.post("/admin/venues/{venue_id}/stock/{menu_item_id}/moves")
async def owner_move(
    menu_item_id: str, body: MoveIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    require_module(venue, "R-INV")
    stock = await inventory.get(uow, venue, menu_item_id)
    await inventory.adjust(uow, venue, stock, body.kind, body.quantity, admin.actor(venue.id))
    return await _one(uow, stock)


@router.get("/stock")
async def staff_stock(ctx: Staff, uow: Uow) -> dict[str, Any]:
    """What is low or out, for the kitchen and the till."""
    require_module(ctx.venue, "R-INV")
    data = await inventory.overview(uow, ctx.venue)
    return {"items": data["items"], "low": data["low"]}


@router.post("/stock/{menu_item_id}/moves")
async def staff_move(menu_item_id: str, body: MoveIn, ctx: Staff, uow: Uow) -> dict[str, Any]:
    """Kitchen logs waste (dropped, burnt, expired); staff log deliveries and shelf counts."""
    require_module(ctx.venue, "R-INV")
    if ctx.device.type != "kds" and ctx.staff is None:
        raise Forbidden("Staff PIN login required")
    stock = await inventory.get(uow, ctx.venue, menu_item_id)
    await inventory.adjust(uow, ctx.venue, stock, body.kind, body.quantity, ctx.actor)
    return await _one(uow, stock)
