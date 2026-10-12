"""Slips (receipt, order-number slip, kitchen ticket) and the cloud print queue.

A slip becomes one PrintJob per printer that has its role (kitchen tickets go to the printers of
the stations on the ticket). How a job reaches paper depends on the printer's connection:

  cloud   the printer polls us (Star CloudPRNT) and fetches the job itself
  screen  the host screen is told on its device topic and prints over USB / Bluetooth
  file    written to PRINT_DIR (testing)

A venue with no printers set up keeps the old per-role settings (dev and tests: files).
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select

from kiosk.config import settings
from kiosk.infra.models import Invoice, Order, Printer, PrintJob, Venue, utcnow
from kiosk.infra.printing import EscPos, FilePrinter, NetworkPrinter, Slip, build_printer
from kiosk.services.uow import UnitOfWork

log = structlog.get_logger()
_tasks: set[asyncio.Task[None]] = set()


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def _en(name: dict[str, Any]) -> str:
    return str(name.get("en") or next(iter(name.values()), ""))


def render_receipt(venue: Venue, order: Order, invoice: Invoice | None, drawer: bool) -> Slip:
    p = EscPos().align("center").bold().size(2, 2).text(venue.name).size().bold(False)
    if venue.setting("legal_name"):
        p.text(str(venue.setting("legal_name")))
    if venue.setting("vat_number"):
        p.text(f"VAT Reg. No: {venue.setting('vat_number')}")
    if invoice:
        p.text(f"{'Tax invoice' if venue.setting('vat_number') else 'Invoice'} {invoice.number}")
    p.text(order.created_at.strftime("%Y-%m-%d %H:%M UTC")).align("left").rule()
    for item in order.items:
        if item.kds_status == "voided":
            continue
        if item.parent_position is not None:  # part of a combo, priced on the combo line
            p.text(f"   + {_en(item.name)}")
            continue
        p.row(f"{item.quantity} x {_en(item.name)}", money(item.line_total))
        for mod in item.modifiers:
            p.text(f"   + {_en(mod['name'])}")
    p.rule().row("Subtotal", money(order.subtotal))
    if order.discount_total:
        p.row(order.discount_label or "Discount", f"-{money(order.discount_total)}")
    for t in order.tax_lines:
        label = _en(t["name"]) if len(_en(t["name"])) <= 24 else str(t.get("code") or _en(t["name"]))
        p.row(f"{label} ({t['rate_bp'] / 100:g}%)", money(t["amount"]))
    p.bold().row("TOTAL LKR", money(order.total)).bold(False)
    for pay in order.payments:
        if pay.status != "succeeded":
            continue
        sign = "-" if pay.kind == "refund" else ""
        p.row(f"{pay.kind.title()} {pay.method}", f"{sign}{money(pay.amount)}")
        if pay.change_given:
            p.row("Change", money(pay.change_given))
    p.rule().align("center").text("Your number").bold().size(3, 3).text(order.token)
    if order.points_earned:
        p.text(f"Points earned: {order.points_earned}")
    p.size().bold(False).text(str(venue.setting("receipt_footer") or "Thank you!")).feed().cut()
    if drawer:
        p.kick_drawer()
    return p.bytes()


def render_bill(venue: Venue, table_ref: str, orders: list[Order]) -> Slip:
    """The bill the waiter brings to the table before payment (not a receipt / tax invoice)."""
    p = EscPos().align("center").bold().size(2, 2).text(venue.name).size().bold(False)
    p.bold().size(2, 1).text(f"BILL  Table {table_ref}").size().bold(False)
    p.text(utcnow().strftime("%Y-%m-%d %H:%M UTC")).align("left").rule()
    subtotal = discount = tax = total = paid = 0
    taxes: dict[str, int] = {}
    for o in orders:
        for item in o.items:
            if item.kds_status == "voided":
                continue
            if item.parent_position is not None:
                p.text(f"   + {_en(item.name)}")
                continue
            p.row(f"{item.quantity} x {_en(item.name)}", money(item.line_total))
            for mod in item.modifiers:
                p.text(f"   + {_en(mod['name'])}")
        subtotal += o.subtotal
        discount += o.discount_total
        tax += o.tax_total
        total += o.total
        paid += o.paid_total
        for t in o.tax_lines:
            key = f"{_en(t['name'])} ({t['rate_bp'] / 100:g}%)"
            taxes[key] = taxes.get(key, 0) + t["amount"]
    p.rule().row("Subtotal", money(subtotal))
    if discount:
        p.row("Discount", f"-{money(discount)}")
    for k, v in taxes.items():
        p.row(k if len(k) <= 30 else k[:30], money(v))
    p.bold().size(1, 2).row("TOTAL LKR", money(total)).size().bold(False)
    if paid:
        p.row("Already paid", f"-{money(paid)}").bold().row("TO PAY", money(total - paid)).bold(False)
    p.rule().align("center").text("This is not a receipt.").text("Pay your waiter: cash, card or QR.")
    return p.feed().cut().bytes()


def render_token(venue: Venue, order: Order) -> Slip:
    p = EscPos().align("center").text(venue.name).text("Your order number")
    p.bold().size(4, 4).text(order.token).size().bold(False)
    if order.payment_status != "paid":
        p.text("Please pay at the cashier").barcode(order.id)
    return p.feed().cut().bytes()


def render_kitchen_ticket(order: Order, stations: list[str] | None = None) -> Slip:
    """The whole order, or only the items of the given stations (a station's own printer)."""
    where = f"Table {order.table_ref}" if order.table_ref else order.channel.title()
    p = EscPos().bold().size(2, 2).text(f"#{order.token}  {where}").size().bold(False).rule()
    for item in order.items:
        if item.kds_status == "voided" or item.station == "none":  # combo line: its parts follow
            continue
        if stations and item.station not in stations:
            continue
        p.bold().text(f"{item.quantity} x {_en(item.name)}  [{item.station}]").bold(False)
        for mod in item.modifiers:
            p.text(f"   + {_en(mod['name'])}")
        if item.notes:
            p.bold().text(f"   NOTE: {item.notes}").bold(False)
        if item.allergens:
            p.bold().text(f"   ALLERGENS: {', '.join(item.allergens)}").bold(False)
    return p.feed().cut().bytes()


def render_test(venue: Venue, printer: Printer) -> Slip:
    p = EscPos().align("center").bold().size(2, 2).text("TEST PRINT").size().bold(False)
    p.text(venue.name).text(printer.name).align("left").rule()
    p.row("Prints", ", ".join(printer.roles) or "-")
    if printer.stations:
        p.row("Stations", ", ".join(printer.stations))
    p.row("Connection", printer.connection).row("Paper", f"{printer.paper_mm} mm")
    p.row("Time", utcnow().strftime("%Y-%m-%d %H:%M UTC")).rule()
    p.align("center").text("If you can read this, the printer works.")
    p.barcode("TEST-1234").feed().cut()
    if printer.cash_drawer:
        p.kick_drawer()
    return p.bytes()


def _has_items_for(order: Order, stations: list[str]) -> bool:
    return any(i.station in stations and i.kds_status != "voided" for i in order.items)


async def enqueue(
    uow: UnitOfWork,
    venue: Venue,
    role: str,
    slip: Slip,
    label: str,
    order: Order | None = None,
    source: str | None = None,
) -> list[PrintJob]:
    """Queue a slip on the printers that should print it. Returns the jobs (none: legacy printing).

    Kitchen tickets go to every kitchen printer (of the ticket's stations). Receipts and number
    slips print where the guest is: on the printer of the screen they came from (source: the kiosk's
    own printer, the till's printer), else on the shared printers (not tied to a screen).
    """
    printers = (
        await uow.session.scalars(select(Printer).where(Printer.venue_id == venue.id, Printer.is_active))
    ).all()
    if not printers:
        uow.after_commit.append(job(venue, role, slip, label))
        return []
    targets = [p for p in printers if role in p.roles]
    if not targets and role == "token":  # no number-slip printer: the receipt printer prints them
        targets = [p for p in printers if "receipt" in p.roles]
    if role != "kitchen":
        own = [p for p in targets if source and p.device_id == source]
        shared = [p for p in targets if p.device_id is None]
        # A waiter's phone has no printer: print at the counter (the POS's printer), never nowhere.
        targets = own or shared or targets[:1]
    uow.printed.extend(p.name for p in targets)
    jobs = []
    for printer in targets:
        data = slip
        if role == "kitchen" and printer.stations and order is not None:
            if not _has_items_for(order, printer.stations):
                continue
            data = render_kitchen_ticket(order, printer.stations)
        jobs.append(queue_on(uow, venue, printer, data, label))
    return jobs


def queue_on(uow: UnitOfWork, venue: Venue, printer: Printer, slip: Slip, label: str) -> PrintJob:
    job_ = PrintJob(
        venue_id=venue.id, printer_id=printer.id, label=label[:80], escpos=bytes(slip), text=slip.text
    )
    uow.session.add(job_)
    if printer.connection == "screen" and printer.device_id:
        uow.after_commit.append(_announce(uow, venue.id, printer.device_id, job_))
    elif printer.connection == "file":
        uow.after_commit.append(_to_file(job_))
    elif printer.connection == "network":
        uow.after_commit.append(_to_network(venue.id, printer, job_))
    return job_


def _to_network(venue_id: str, printer: Printer, job_: PrintJob) -> Callable[[], Awaitable[None]]:
    """A printer on the restaurant's network: this server (the restaurant's hub) sends the job to it
    straight away (raw TCP 9100), so kitchen tickets keep printing without internet. A cloud server
    can't reach inside the restaurant: it says so, and the staff reprint once the hub is back."""
    host, port, name, data, label = (
        printer.host or "",
        printer.port or 9100,
        printer.name,
        job_.escpos,
        job_.label,
    )

    async def deliver() -> None:
        ok, error, tries = False, None, 0
        if not settings.is_edge:
            error = "This printer is printed by the restaurant's hub, which isn't connected"
        else:
            for tries in range(1, 4):
                try:
                    await NetworkPrinter(host, port).send(data, label)
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001 - unreachable, refused, timeout...
                    error = f"No answer from {host}:{port} ({type(exc).__name__})"
                    await asyncio.sleep(1.0 * tries)
        from kiosk.infra.db import session_factory
        from kiosk.realtime.hub import hub

        async with session_factory()() as session:
            row = await session.get(PrintJob, job_.id)
            target = await session.get(Printer, printer.id)
            if row is not None:
                row.attempts = (row.attempts or 0) + max(tries, 1)
                finish(row, ok, error)
            if target is not None:
                if ok:
                    target.last_seen_at, target.last_status = utcnow(), {}
                else:
                    target.last_status = {"error": error}
            await session.commit()
        if not ok:
            log.warning("print.failed", printer=name, label=label, error=error)
            await hub.publish(
                venue_id,
                "print.failed",
                {"printer": name, "error": error, "label": label},
                ["orders", "kds"],
            )

    async def run() -> None:
        if settings.print_async:  # never hold up the order while a printer answers
            task = asyncio.create_task(deliver())
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
        else:
            await deliver()

    return run


def _announce(
    uow: UnitOfWork, venue_id: str, device_id: str, job_: PrintJob
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        from kiosk.realtime.hub import hub

        await hub.publish(
            venue_id, "print.job", {"job_id": job_.id, "label": job_.label}, [f"device:{device_id}"]
        )

    return run


def _to_file(job_: PrintJob) -> Callable[[], Awaitable[None]]:
    data, label = job_.escpos, job_.label

    async def run() -> None:
        try:
            await FilePrinter(settings.print_dir).send(data, label)
        except OSError as exc:
            log.warning("print.failed", label=label, error=str(exc))

    return run


def finish(job_: PrintJob, ok: bool, error: str | None = None, at: datetime | None = None) -> None:
    job_.status = "done" if ok else "failed"
    job_.error = None if ok else (error or "failed")[:300]
    job_.printed_at = (at or utcnow()) if ok else None


def job_dict(j: PrintJob) -> dict[str, Any]:
    return {
        "id": j.id,
        "printer_id": j.printer_id,
        "label": j.label,
        "status": j.status,
        "attempts": j.attempts,
        "error": j.error,
        "created_at": j.created_at.isoformat(),
        "printed_at": j.printed_at.isoformat() if j.printed_at else None,
    }


async def _send(venue: Venue, role: str, data: bytes, label: str) -> None:
    printers: dict[str, Any] = venue.setting("printers")
    config = printers.get(role) or printers.get("receipt" if role == "token" else role) or {"type": "file"}
    printer = build_printer(config, settings.print_dir)
    try:
        await printer.send(data, label)
    except Exception as exc:  # noqa: BLE001
        log.warning("print.failed", role=role, label=label, error=str(exc))


def job(venue: Venue, role: str, data: bytes, label: str) -> Callable[[], Awaitable[None]]:
    """Legacy (no printers set up): an after-commit callback that prints from the server."""

    async def run() -> None:
        if settings.print_async:
            task = asyncio.create_task(_send(venue, role, data, label))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
        else:
            await _send(venue, role, data, label)

    return run
