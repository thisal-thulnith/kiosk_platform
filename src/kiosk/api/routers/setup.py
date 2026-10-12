"""Setup at install: payments, printers, go-live checklist; plus how printers get their jobs.

Admin (Setup console):   /v1/admin/venues/{id}/payment-setup..., /printers..., /setup-checklist
Screens with a printer:  /v1/print/...   (USB printer on a cashier / kitchen screen)
Cloud printers:          /v1/cloudprnt/{token}   (Star CloudPRNT: poll, fetch, confirm)
"""

import base64
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from kiosk.api.deps import Admin, AdminVenue, Ctx, Uow, installer_ctx
from kiosk.api.routers.admin_org import bump_config
from kiosk.auth.security import token_digest
from kiosk.errors import AppError, NotFound
from kiosk.infra.models import DEFAULT_VENUE_SETTINGS, Device, Printer, PrintJob, utcnow
from kiosk.services import printing
from kiosk.services import setup as svc

# Everything here is done by our installation team (platform login), never by the restaurant.
admin_router = APIRouter(
    prefix="/v1/admin/venues/{venue_id}", tags=["setup"], dependencies=[Depends(installer_ctx)]
)
router = APIRouter(prefix="/v1", tags=["printing"])


# ------------------------------------------------------------------ payments


class MethodsIn(BaseModel):
    cash: bool
    lankaqr: bool
    card: bool


class LankaQrIn(BaseModel):
    provider: str = "mock"
    merchant_id: str = Field("", max_length=80)
    secret: str | None = Field(None, max_length=500, description="API key; leave empty to keep the saved one")
    live: bool = False


@admin_router.get("/payment-setup")
async def payment_setup(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    return await svc.payment_overview(uow, venue)


@admin_router.put("/payment-setup/methods")
async def set_methods(body: MethodsIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    if not any(body.model_dump().values()):
        raise AppError("bad_setting", "Keep at least one way to pay")
    venue.settings = {**(venue.settings or {}), "payment_methods": body.model_dump()}
    bump_config(venue)
    uow.audit(admin.actor(venue.id), "payments.methods", venue.id, **body.model_dump())
    uow.emit(
        venue.id,
        "venue.settings",
        {"settings": {**DEFAULT_VENUE_SETTINGS, **venue.settings}},
        ["orders", "menu", "status", "kds", "service"],
    )
    await uow.commit()
    return await svc.payment_overview(uow, venue)


@admin_router.put("/payment-setup/lankaqr")
async def save_lankaqr(body: LankaQrIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    account = await svc.save_lankaqr(
        uow, venue, admin.actor(venue.id), body.provider, body.merchant_id, body.secret, body.live
    )
    await uow.commit()
    return svc.account_dict(account)


@admin_router.post("/payment-setup/lankaqr/test")
async def test_lankaqr(venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    account = await svc.test_lankaqr(uow, venue, admin.actor(venue.id))
    await uow.commit()
    return svc.account_dict(account)


@admin_router.post("/devices/{device_id}/card-test")
async def test_reader(device_id: str, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    result = await svc.test_reader(uow, device, admin.actor(venue.id))
    await uow.commit()
    return result


# ------------------------------------------------------------------ printers


class PrinterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    connection: Literal["cloud", "screen", "network", "file"]
    roles: list[Literal["receipt", "token", "kitchen"]] = Field(min_length=1)
    stations: list[str] = []
    device_id: str | None = None
    host: str | None = Field(
        default=None, max_length=120, description="Network printers: its IP, e.g. 192.168.1.50"
    )
    port: int = Field(default=9100, ge=1, le=65535)
    paper_mm: int = 80
    cash_drawer: bool = False


class PrinterPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    roles: list[Literal["receipt", "token", "kitchen"]] | None = None
    stations: list[str] | None = None
    device_id: str | None = None
    host: str | None = Field(default=None, max_length=120)
    port: int | None = Field(default=None, ge=1, le=65535)
    paper_mm: int | None = None
    cash_drawer: bool | None = None
    is_active: bool | None = None


async def _one(uow: Uow, venue_id: str, printer_id: str) -> dict[str, Any]:
    return next(p for p in await svc.list_printers(uow, venue_id) if p["id"] == printer_id)


@admin_router.get("/printers")
async def list_printers(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    return await svc.list_printers(uow, venue.id)


@admin_router.post("/printers", status_code=201)
async def add_printer(body: PrinterIn, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    printer = await svc.add_printer(uow, venue, admin.actor(venue.id), body.model_dump())
    if printer.connection == "screen" and printer.device_id:
        # The host screen shows "Connect printer" so the installer can plug it in and tap once.
        uow.emit(
            venue.id,
            "device.command",
            {"device_id": printer.device_id, "command": "connect_printer"},
            [f"device:{printer.device_id}"],
        )
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return await _one(uow, venue.id, printer.id)


@admin_router.patch("/printers/{printer_id}")
async def update_printer(
    printer_id: str, body: PrinterPatch, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    printer = await svc.get_printer(uow, venue.id, printer_id)
    await svc.update_printer(uow, venue, printer, admin.actor(venue.id), body.model_dump(exclude_none=True))
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return await _one(uow, venue.id, printer.id)


@admin_router.delete("/printers/{printer_id}")
async def remove_printer(printer_id: str, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    printer = await svc.get_printer(uow, venue.id, printer_id)
    jobs = (await uow.session.scalars(select(PrintJob).where(PrintJob.printer_id == printer.id))).all()
    for j in jobs:
        await uow.session.delete(j)
    await uow.session.delete(printer)
    uow.audit(admin.actor(venue.id), "printer.removed", printer_id)
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return {"id": printer_id, "removed": True}


@admin_router.post("/printers/{printer_id}/test", status_code=202)
async def test_printer(printer_id: str, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    printer = await svc.get_printer(uow, venue.id, printer_id)
    job = await svc.print_test(uow, venue, printer, admin.actor(venue.id))
    await uow.commit()
    return printing.job_dict(job)


@admin_router.post("/printers/{printer_id}/confirm")
async def confirm_printed(printer_id: str, venue: AdminVenue, admin: Admin, uow: Uow) -> dict[str, Any]:
    """The installer saw the test page come out (for printers that cannot report back)."""
    printer = await svc.get_printer(uow, venue.id, printer_id)
    printer.tested_at = utcnow()
    uow.audit(admin.actor(venue.id), "printer.confirmed", printer.id)
    bump_config(venue)  # hubs pick up the change
    await uow.commit()
    return await _one(uow, venue.id, printer.id)


@admin_router.get("/printers/{printer_id}/jobs")
async def printer_jobs(printer_id: str, venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    printer = await svc.get_printer(uow, venue.id, printer_id)
    rows = (
        await uow.session.scalars(
            select(PrintJob)
            .where(PrintJob.printer_id == printer.id)
            .order_by(PrintJob.created_at.desc())
            .limit(20)
        )
    ).all()
    return [printing.job_dict(j) for j in rows]


class HardwareIn(BaseModel):
    model: str
    card_terminal_id: str | None = Field(None, max_length=80)


@admin_router.put("/devices/{device_id}/hardware")
async def set_hardware(
    device_id: str, body: HardwareIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> dict[str, Any]:
    """What this screen is (e.g. all-in-one kiosk): its built-in printer, reader and scanner in one go."""
    device = await uow.session.get(Device, device_id)
    if device is None or device.venue_id != venue.id:
        raise NotFound("Device")
    result = await svc.apply_hardware_model(
        uow, venue, device, body.model, body.card_terminal_id, admin.actor(venue.id)
    )
    bump_config(venue)
    if result["printer_id"]:
        uow.emit(
            venue.id,
            "device.command",
            {"device_id": device.id, "command": "connect_printer"},
            [f"device:{device.id}"],
        )
    await uow.commit()
    return result


class InstalledIn(BaseModel):
    item: str
    count: int = Field(ge=0, le=50)


@admin_router.get("/equipment")
async def equipment(venue: AdminVenue, uow: Uow) -> list[dict[str, Any]]:
    return await svc.equipment(uow, venue)


@admin_router.put("/equipment")
async def confirm_equipment(
    body: InstalledIn, venue: AdminVenue, admin: Admin, uow: Uow
) -> list[dict[str, Any]]:
    await svc.confirm_hardware(uow, venue, admin.actor(venue.id), body.item, body.count)
    await uow.commit()
    return await svc.equipment(uow, venue)


@admin_router.get("/setup-checklist")
async def checklist(venue: AdminVenue, uow: Uow) -> dict[str, Any]:
    return await svc.checklist(uow, venue)


# ------------------------------------------------------------------ screen-attached printers


async def _my_job(uow: Uow, ctx: Any, job_id: str) -> tuple[PrintJob, Printer]:
    job = await uow.session.get(PrintJob, job_id)
    printer = await uow.session.get(Printer, job.printer_id) if job else None
    if job is None or printer is None or printer.device_id != ctx.device.id:
        raise NotFound("Print job")
    return job, printer


def _job_payload(job: PrintJob, printer: Printer) -> dict[str, Any]:
    return {
        **printing.job_dict(job),
        "printer": {"id": printer.id, "name": printer.name, "paper_mm": printer.paper_mm},
        "escpos_b64": base64.b64encode(job.escpos).decode(),
        "text": job.text,
    }


@router.get("/print/printers")
async def my_printers(ctx: Ctx, uow: Uow) -> list[dict[str, Any]]:
    """Printers plugged into this screen."""
    rows = (
        await uow.session.scalars(
            select(Printer).where(
                Printer.device_id == ctx.device.id, Printer.is_active, Printer.connection == "screen"
            )
        )
    ).all()
    return [{"id": p.id, "name": p.name, "roles": p.roles, "paper_mm": p.paper_mm} for p in rows]


@router.get("/print/jobs")
async def my_jobs(ctx: Ctx, uow: Uow) -> list[dict[str, Any]]:
    """Jobs waiting for this screen's printer (also those queued while the screen was off)."""
    rows = (
        await uow.session.execute(
            select(PrintJob, Printer)
            .join(Printer, Printer.id == PrintJob.printer_id)
            .where(Printer.device_id == ctx.device.id, PrintJob.status.in_(["queued", "sent"]))
            .order_by(PrintJob.created_at)
            .limit(20)
        )
    ).all()
    return [_job_payload(j, p) for j, p in rows]


@router.get("/print/jobs/{job_id}")
async def my_job(job_id: str, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    job, printer = await _my_job(uow, ctx, job_id)
    job.status, job.attempts = "sent", job.attempts + 1
    await uow.commit()
    return _job_payload(job, printer)


class ResultIn(BaseModel):
    ok: bool
    error: str | None = Field(None, max_length=300)


@router.post("/print/jobs/{job_id}/result")
async def job_result(job_id: str, body: ResultIn, ctx: Ctx, uow: Uow) -> dict[str, Any]:
    job, printer = await _my_job(uow, ctx, job_id)
    printing.finish(job, body.ok, body.error)
    printer.last_seen_at = utcnow()
    printer.last_status = {"ok": body.ok, "error": body.error}
    svc.job_finished(printer, job)
    if not body.ok:
        uow.emit(
            ctx.venue.id,
            "print.failed",
            {"printer": printer.name, "label": job.label, "error": body.error},
            ["orders", "kds"],
        )
    await uow.commit()
    return printing.job_dict(job)


# ------------------------------------------------------------------ Star CloudPRNT


async def _cloud_printer(uow: Uow, token: str) -> Printer:
    printer = await uow.session.scalar(select(Printer).where(Printer.token_digest == token_digest(token)))
    if printer is None or not printer.is_active or printer.connection != "cloud":
        raise NotFound("Printer")
    return printer


async def _next_job(uow: Uow, printer: Printer) -> PrintJob | None:
    return await uow.session.scalar(
        select(PrintJob)
        .where(PrintJob.printer_id == printer.id, PrintJob.status.in_(["queued", "sent"]))
        .order_by(PrintJob.created_at)
        .limit(1)
    )


@router.post("/cloudprnt/{printer_token}", include_in_schema=False)
async def cloudprnt_poll(
    printer_token: str, uow: Uow, status: Annotated[dict[str, Any] | None, Body()] = None
) -> dict[str, Any]:
    """The printer asks every few seconds: anything to print? It also reports paper / cover state."""
    printer = await _cloud_printer(uow, printer_token)
    printer.last_seen_at = utcnow()
    body = status or {}
    printer.last_status = {
        k: body[k] for k in ("statusCode", "printerMAC", "status", "printingInProgress") if k in body
    }
    job = await _next_job(uow, printer)
    await uow.commit()
    if job is None:
        return {"jobReady": False}
    return {"jobReady": True, "mediaTypes": ["text/plain"], "jobToken": job.id}


@router.get("/cloudprnt/{printer_token}", include_in_schema=False)
async def cloudprnt_fetch(
    printer_token: str,
    uow: Uow,
    type_: Annotated[str, Query(alias="type")] = "text/plain",
    job_token: Annotated[str | None, Query(alias="token")] = None,
) -> Response:
    printer = await _cloud_printer(uow, printer_token)
    job = await uow.session.get(PrintJob, job_token) if job_token else await _next_job(uow, printer)
    if job is None or job.printer_id != printer.id:
        return Response(status_code=404)
    if type_ != "text/plain":
        return Response(status_code=415)
    job.status, job.attempts = "sent", job.attempts + 1
    await uow.commit()
    return Response(content=job.text, media_type="text/plain; charset=utf-8")


@router.delete("/cloudprnt/{printer_token}", include_in_schema=False)
async def cloudprnt_done(
    printer_token: str,
    uow: Uow,
    code: str = "200 OK",
    job_token: Annotated[str | None, Query(alias="token")] = None,
) -> dict[str, Any]:
    """Printed (code 2xx) or failed (anything else, e.g. "520 Printer Error")."""
    printer = await _cloud_printer(uow, printer_token)
    job = await uow.session.get(PrintJob, job_token) if job_token else None
    if job is None:
        job = await uow.session.scalar(
            select(PrintJob)
            .where(PrintJob.printer_id == printer.id, PrintJob.status == "sent")
            .order_by(PrintJob.created_at)
            .limit(1)
        )
    if job is None or job.printer_id != printer.id:
        return {"ok": False}
    ok = code.strip().startswith("2")
    printing.finish(job, ok, None if ok else code)
    printer.last_seen_at = utcnow()
    svc.job_finished(printer, job)
    if not ok:
        uow.emit(
            printer.venue_id,
            "print.failed",
            {"printer": printer.name, "label": job.label, "error": code},
            ["orders", "kds"],
        )
    await uow.commit()
    return {"ok": True}
