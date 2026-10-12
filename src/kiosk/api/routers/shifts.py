from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from kiosk.api.deps import DeviceCtx, Uow, require_device, require_staff
from kiosk.errors import NotFound
from kiosk.services import shifts as svc
from kiosk.services.payments import open_shift_for

router = APIRouter(prefix="/v1/shifts", tags=["cash shifts"])


async def cashier_device(
    ctx: Annotated[DeviceCtx, Depends(require_staff("cashier", "waiter"))],
) -> DeviceCtx:
    """The POS drawer, or a waiter's own cash bag (cash collected at the tables)."""
    return await require_device("cashier", "waiter")(ctx)


CashierDevice = Annotated[DeviceCtx, Depends(cashier_device)]


class OpenIn(BaseModel):
    opening_float: int = Field(ge=0, description="LKR cents in the drawer at start")


class CloseIn(BaseModel):
    counted_cash: int = Field(ge=0, description="LKR cents counted at close")


@router.post("/open", status_code=201)
async def open_shift(body: OpenIn, ctx: CashierDevice, uow: Uow) -> dict[str, Any]:
    shift = await svc.open_shift(uow, ctx.actor, body.opening_float)
    await uow.commit()
    return svc.shift_dict(shift)


@router.get("/current")
async def current_shift(ctx: CashierDevice, uow: Uow) -> dict[str, Any]:
    shift = await open_shift_for(uow, ctx.venue.id, ctx.device.id)
    if shift is None:
        raise NotFound("Open shift")
    report = await svc.shift_report(uow, shift)
    return {**svc.shift_dict(shift), "live": report}


@router.post("/{shift_id}/close")
async def close_shift(shift_id: str, body: CloseIn, ctx: CashierDevice, uow: Uow) -> dict[str, Any]:
    shift = await svc.close_shift(uow, ctx.actor, shift_id, body.counted_cash)
    await uow.commit()
    return svc.shift_dict(shift)
