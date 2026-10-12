"""Plans in the database: screen limits, module checks, slot creation, quotes."""

from typing import Any

from sqlalchemy import func, select

from kiosk.config import settings
from kiosk.domain.modules import DEVICE_MODULE, has_module, quote, screen_limit
from kiosk.errors import AppError
from kiosk.infra.models import Device, PriceBook, Venue
from kiosk.services.uow import UnitOfWork

SLOT_NAMES = {
    "kds": "Kitchen",
    "status": "Status board",
    "kiosk": "Kiosk",
    "cashier": "Cashier",
    "waiter": "Waiter",
    "board": "Menu board",
}
# Screen types that have screens today; boards and room kiosks get slots once those screens exist.
SLOT_TYPES = ("table", "kds", "status", "kiosk", "cashier", "waiter", "board")


def require_module(venue: Venue, code: str) -> None:
    if not has_module(venue.plan, code):
        raise AppError("module_not_in_plan", f"This venue's package does not include {code}", 403)


async def screens_in_use(uow: UnitOfWork, venue_id: str) -> dict[str, int]:
    rows = await uow.session.execute(
        select(Device.type, func.count())
        .where(Device.venue_id == venue_id, Device.is_active)
        .group_by(Device.type)
    )
    return {t: int(n) for t, n in rows.all()}


async def check_screen_limit(uow: UnitOfWork, venue: Venue, device_type: str) -> None:
    """Refuse one screen more than the venue's package allows."""
    if device_type in settings.coming_soon_types:
        names = {"kiosk": "Self-order kiosks", "status": "Order status boards"}
        raise AppError("coming_soon", f"{names.get(device_type, device_type)} are coming soon", 403)
    limit = screen_limit(venue.plan, device_type)
    if limit is None:
        return
    module = DEVICE_MODULE.get(device_type)
    if (
        module
        and not has_module(venue.plan, module)
        and not (device_type == "kds" and has_module(venue.plan, "H-KDS"))
    ):
        raise AppError("module_not_in_plan", f"The package has no {device_type} screens ({module})", 403)
    used = (await screens_in_use(uow, venue.id)).get(device_type, 0)
    if used >= limit:
        raise AppError(
            "screen_limit",
            f"The package includes {limit} {device_type} screen(s) and all are in use. "
            "Add more screens to the package, or disable one first",
            403,
        )


async def usage(uow: UnitOfWork, venue: Venue) -> dict[str, dict[str, int | None]]:
    """Per screen type: slots in use (active screens), how many are set up, and the package limit."""
    used = await screens_in_use(uow, venue.id)
    rows = await uow.session.execute(
        select(Device.type, func.count())
        .where(Device.venue_id == venue.id, Device.is_active, Device.token_hash.is_not(None))
        .group_by(Device.type)
    )
    paired = {t: int(n) for t, n in rows.all()}
    kinds = set(used) | set((venue.plan or {}).get("screens", {}))
    return {
        k: {"used": used.get(k, 0), "set_up": paired.get(k, 0), "limit": screen_limit(venue.plan, k)}
        for k in sorted(kinds)
    }


async def create_slots(uow: UnitOfWork, venue: Venue) -> list[Device]:
    """Create unpaired screen slots for everything in the package (Table T1..Tn, Kitchen 1, ...),
    so installers only pick "which screen is this?" on site."""
    plan = venue.plan or {}
    every = (await uow.session.scalars(select(Device).where(Device.venue_id == venue.id))).all()
    made = []
    for kind in SLOT_TYPES:
        want = int(plan.get("screens", {}).get(kind, 0))
        have = [d for d in every if d.type == kind and d.is_active]
        # Table numbers of disabled screens stay reserved, so a new slot never duplicates one.
        taken_tables = {d.table_ref for d in every if d.type == "table"}
        n = 1
        while len(have) < want:
            if kind == "table":
                while f"T{n}" in taken_tables:
                    n += 1
                d = Device(venue_id=venue.id, type="table", name=f"Table T{n}", table_ref=f"T{n}")
                taken_tables.add(f"T{n}")
            else:
                d = Device(venue_id=venue.id, type=kind, name=f"{SLOT_NAMES[kind]} {len(have) + 1}")
            uow.session.add(d)
            have.append(d)
            made.append(d)
    await uow.session.flush()
    return made


async def price_book(uow: UnitOfWork) -> dict[str, dict[str, int]]:
    rows = (await uow.session.scalars(select(PriceBook))).all()
    return {r.item: {"monthly": r.monthly, "once": r.once} for r in rows}


async def make_quote(uow: UnitOfWork, plan: dict[str, Any]) -> dict[str, Any]:
    return quote(plan, await price_book(uow))
