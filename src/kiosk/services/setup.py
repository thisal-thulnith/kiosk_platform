"""Install-time setup done by our team (or the owner): payments, printers, and the go-live checklist.

The flow an installer follows, in the Setup console:

  1. Payments  - switch methods on or off, enter the LankaQR merchant ID and key, "Test connection";
                 for each screen with a card reader, "Test reader".
  2. Printers  - add each printer with what it prints (receipts, number slips, kitchen tickets for
                 some or all stations, cash drawer) and how it is connected:
                   cloud  (Star CloudPRNT): type the URL shown into the printer's settings page
                   screen (USB / Bluetooth): plug it into the cashier or kitchen screen and tap
                          "Connect printer" there once
                 then "Print test page" -> the test page prints -> the printer is ticked.
  3. Checklist - everything above plus menu, taxes, business details, staff, screens and one
                 real test order, each with a tick or what is still missing.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from kiosk.auth.security import new_token, token_digest
from kiosk.config import settings
from kiosk.domain.modules import HARDWARE, HARDWARE_MODELS, requirements
from kiosk.errors import AppError, NotFound
from kiosk.infra import secrets
from kiosk.infra.gateway import PROVIDERS, GatewayError, get_gateway
from kiosk.infra.models import (
    PRINT_ROLES,
    PRINTER_CONNECTIONS,
    Device,
    HubStatus,
    MenuItem,
    Order,
    PaymentAccount,
    Printer,
    PrintJob,
    Staff,
    TaxRule,
    Venue,
    utcnow,
)
from kiosk.infra.terminal import TerminalError, get_terminal
from kiosk.realtime.hub import hub
from kiosk.services import hybrid, printing
from kiosk.services.payments import card_setup, method_on
from kiosk.services.uow import Actor, UnitOfWork

# Screens a printer can belong to: USB into the screen, or a cloud printer standing next to it.
PRINTER_HOSTS = ("cashier", "kds", "waiter", "kiosk")
ONLINE_WITHIN = timedelta(minutes=2)  # a cloud printer polls every few seconds


# ------------------------------------------------------------------ payments


async def lankaqr_account(uow: UnitOfWork, venue_id: str) -> PaymentAccount | None:
    return await uow.session.scalar(
        select(PaymentAccount).where(PaymentAccount.venue_id == venue_id, PaymentAccount.kind == "lankaqr")
    )


def account_dict(a: PaymentAccount | None) -> dict[str, Any]:
    if a is None:
        return {"provider": None, "merchant_id": "", "secret_hint": None, "live": False, "status": "not_set"}
    return {
        "provider": a.provider,
        "merchant_id": a.merchant_id,
        "secret_hint": a.secret_hint,
        "live": a.live,
        "status": a.status,
        "checked_at": a.checked_at.isoformat() if a.checked_at else None,
        "last_error": a.last_error,
    }


async def save_lankaqr(
    uow: UnitOfWork,
    venue: Venue,
    actor: Actor,
    provider: str,
    merchant_id: str,
    secret: str | None,
    live: bool,
) -> PaymentAccount:
    if provider not in PROVIDERS:
        raise AppError("bad_provider", f"Unknown payment provider {provider}")
    account = await lankaqr_account(uow, venue.id)
    if account is None:
        account = PaymentAccount(venue_id=venue.id, kind="lankaqr", provider=provider)
        uow.session.add(account)
    changed = (account.provider, account.merchant_id, account.live) != (provider, merchant_id, live)
    account.provider, account.merchant_id, account.live = provider, merchant_id.strip(), live
    if secret:
        account.secret_enc, account.secret_hint = secrets.encrypt(secret), secret[-4:]
        changed = True
    if changed:  # new details must be tested again
        account.status, account.checked_at, account.last_error = "not_tested", None, None
    uow.audit(actor, "payments.lankaqr_saved", venue.id, provider=provider, live=live)
    return account


async def test_lankaqr(uow: UnitOfWork, venue: Venue, actor: Actor) -> PaymentAccount:
    account = await lankaqr_account(uow, venue.id)
    if account is None:
        raise AppError("not_set_up", "Enter the QR payment merchant details first")
    secret = secrets.decrypt(account.secret_enc) if account.secret_enc else None
    try:
        await get_gateway().check(account.merchant_id, secret, account.live)
        account.status, account.last_error = "ok", None
    except GatewayError as exc:
        account.status, account.last_error = "failed", str(exc)[:300]
    account.checked_at = utcnow()
    uow.audit(actor, "payments.lankaqr_tested", venue.id, status=account.status)
    return account


async def test_reader(uow: UnitOfWork, device: Device, actor: Actor) -> dict[str, Any]:
    card = card_setup(device)
    if card is None:
        raise AppError("no_card_terminal", "This screen has no card payments set up")
    result: dict[str, Any] = {"device_id": device.id, "mode": card["mode"]}
    try:
        if card["mode"] == "reader":
            await get_terminal().ping(card["terminal_id"])
        ok, error = True, None
    except TerminalError as exc:
        ok, error = False, str(exc)
    card = {**card, "tested_at": utcnow().isoformat() if ok else None, "test_error": error}
    device.settings = {**(device.settings or {}), "card": card}
    uow.audit(actor, "payments.reader_tested", device.id, ok=ok)
    return {**result, "ok": ok, "error": error}


async def payment_overview(uow: UnitOfWork, venue: Venue) -> dict[str, Any]:
    devices = (
        await uow.session.scalars(select(Device).where(Device.venue_id == venue.id, Device.is_active))
    ).all()
    return {
        "methods": {m: method_on(venue, m) for m in ("cash", "lankaqr", "card")},
        "lankaqr": account_dict(await lankaqr_account(uow, venue.id)),
        "providers": [{"code": k, "name": n, "needs": needs} for k, (n, needs) in PROVIDERS.items()],
        "card_screens": [
            {
                "device_id": d.id,
                "name": d.name,
                "type": d.type,
                "mode": card["mode"],
                "terminal_id": card.get("terminal_id"),
                "tested_at": card.get("tested_at"),
                "test_error": card.get("test_error"),
            }
            for d in devices
            if (card := card_setup(d))
        ],
    }


# ------------------------------------------------------------------ printers


def cloud_url(token: str) -> str:
    base = (settings.public_url or "").rstrip("/")
    return f"{base}/v1/cloudprnt/{token}"


def printer_dict(p: Printer, host: Device | None = None, queued: int = 0) -> dict[str, Any]:
    now = utcnow()
    online = None
    if p.connection == "cloud":
        online = bool(p.last_seen_at and now - p.last_seen_at < ONLINE_WITHIN)
    elif p.connection == "screen":
        online = bool(host and host.id in hub.connected_devices(p.venue_id))
    token = secrets.decrypt(p.token_enc) if p.token_enc else None
    return {
        "id": p.id,
        "name": p.name,
        "connection": p.connection,
        "roles": p.roles,
        "stations": p.stations,
        "device_id": p.device_id,
        "device_name": host.name if host else None,
        "address": f"{p.host}:{p.port}" if p.connection == "network" and p.host else None,
        "paper_mm": p.paper_mm,
        "cash_drawer": p.cash_drawer,
        "is_active": p.is_active,
        "online": online,
        "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
        "last_status": p.last_status,
        "tested": p.tested_at is not None,
        "tested_at": p.tested_at.isoformat() if p.tested_at else None,
        "queued": queued,
        # Cloud printers: what to type into the printer's CloudPRNT "Server URL" setting.
        "cloud_path": f"/v1/cloudprnt/{token}" if token else None,
        "cloud_url": cloud_url(token) if token and settings.public_url else None,
    }


async def _check_printer(uow: UnitOfWork, venue: Venue, data: dict[str, Any]) -> Device | None:
    if data["connection"] not in PRINTER_CONNECTIONS:
        raise AppError("bad_printer", f"Connection must be one of {', '.join(PRINTER_CONNECTIONS)}")
    if data["connection"] == "file" and not settings.is_dev:
        raise AppError("bad_printer", "File printers are for testing only")
    roles = data.get("roles") or []
    if not roles or any(r not in PRINT_ROLES for r in roles):
        raise AppError("bad_printer", f"Choose what it prints: {', '.join(PRINT_ROLES)}")
    if data.get("stations") and "kitchen" not in roles:
        raise AppError("bad_printer", "Stations only apply to kitchen tickets")
    if data.get("paper_mm", 80) not in (58, 80):
        raise AppError("bad_printer", "Paper must be 58 or 80 mm")
    if data["connection"] == "network":
        address = (data.get("host") or "").strip()
        if not address or not all(ch.isalnum() or ch in ".-:" for ch in address):
            raise AppError("printer_address", "Network printers need their address, e.g. 192.168.1.50")
        if venue.setting("network_mode") != "hybrid" and not settings.is_edge:
            raise AppError(
                "needs_hub",
                "A network printer is printed by the restaurant's hub. Switch the restaurant to Hybrid "
                "and set up the hub first, or use a cloud printer (CloudPRNT) or a USB printer on a screen",
            )
        data["host"] = address
    host = None
    if data["connection"] == "screen" or data.get("device_id"):
        host = await uow.session.get(Device, data.get("device_id") or "")
        if host is None or host.venue_id != venue.id:
            raise AppError("bad_printer", "Choose the screen the printer is plugged into")
        if host.type not in PRINTER_HOSTS:
            raise AppError("bad_printer", "Printers belong to a cashier, kiosk, kitchen or waiter screen")
    return host


async def add_printer(uow: UnitOfWork, venue: Venue, actor: Actor, data: dict[str, Any]) -> Printer:
    await _check_printer(uow, venue, data)
    printer = Printer(
        venue_id=venue.id,
        name=data["name"],
        connection=data["connection"],
        roles=list(dict.fromkeys(data["roles"])),
        stations=list(dict.fromkeys(data.get("stations") or [])),
        device_id=data.get("device_id") if data["connection"] in ("screen", "cloud") else None,
        host=data.get("host") if data["connection"] == "network" else None,
        port=data.get("port") or 9100,
        paper_mm=data.get("paper_mm", 80),
        cash_drawer=bool(data.get("cash_drawer")),
        last_status={},
    )
    if printer.connection == "cloud":
        token = new_token()
        printer.token_digest, printer.token_enc = token_digest(token), secrets.encrypt(token)
    uow.session.add(printer)
    await uow.session.flush()
    uow.audit(actor, "printer.added", printer.id, connection=printer.connection, roles=printer.roles)
    return printer


async def update_printer(
    uow: UnitOfWork, venue: Venue, printer: Printer, actor: Actor, changes: dict[str, Any]
) -> Printer:
    merged = {
        "name": printer.name,
        "connection": printer.connection,
        "roles": printer.roles,
        "stations": printer.stations,
        "device_id": printer.device_id,
        "host": printer.host,
        "port": printer.port,
        "paper_mm": printer.paper_mm,
        "cash_drawer": printer.cash_drawer,
        **changes,
    }
    if merged["connection"] != printer.connection:
        raise AppError("bad_printer", "To change how a printer is connected, remove it and add it again")
    await _check_printer(uow, venue, merged)
    moved = merged["device_id"] != printer.device_id or merged["paper_mm"] != printer.paper_mm
    for k in ("name", "roles", "stations", "device_id", "host", "port", "paper_mm", "cash_drawer"):
        setattr(printer, k, merged[k])
    if "is_active" in changes:
        printer.is_active = bool(changes["is_active"])
    if moved:
        printer.tested_at = None  # test again after moving it to another screen or paper
    uow.audit(actor, "printer.updated", printer.id, **{k: v for k, v in changes.items() if k != "name"})
    return printer


async def get_printer(uow: UnitOfWork, venue_id: str, printer_id: str) -> Printer:
    printer = await uow.session.get(Printer, printer_id)
    if printer is None or printer.venue_id != venue_id:
        raise NotFound("Printer")
    return printer


async def list_printers(uow: UnitOfWork, venue_id: str) -> list[dict[str, Any]]:
    printers = (
        await uow.session.scalars(
            select(Printer).where(Printer.venue_id == venue_id).order_by(Printer.created_at)
        )
    ).all()
    hosts = {
        d.id: d
        for d in (
            await uow.session.scalars(select(Device).where(Device.id.in_({p.device_id for p in printers})))
        ).all()
    }
    queued = dict(
        (
            await uow.session.execute(
                select(PrintJob.printer_id, func.count())
                .where(PrintJob.venue_id == venue_id, PrintJob.status.in_(["queued", "sent"]))
                .group_by(PrintJob.printer_id)
            )
        ).all()
    )
    return [printer_dict(p, hosts.get(p.device_id or ""), int(queued.get(p.id, 0))) for p in printers]


async def print_test(uow: UnitOfWork, venue: Venue, printer: Printer, actor: Actor) -> PrintJob:
    if not printer.is_active:
        raise AppError("printer_off", "Switch the printer on first")
    job = printing.queue_on(uow, venue, printer, printing.render_test(venue, printer), f"test-{printer.id}")
    uow.audit(actor, "printer.test", printer.id)
    await uow.session.flush()
    return job


def job_finished(printer: Printer, job: PrintJob) -> None:
    """A test page that the printer (or its screen) reports as printed ticks the printer."""
    if job.status == "done" and job.label.startswith("test-"):
        printer.tested_at = job.printed_at or utcnow()


# ------------------------------------------------------------------ screen hardware models


async def apply_hardware_model(
    uow: UnitOfWork, venue: Venue, device: Device, model: str, terminal_id: str | None, actor: Actor
) -> dict[str, Any]:
    """Tell us what the screen is (e.g. an all-in-one kiosk): its built-in printer, card reader and
    scanner are set up at once. Returns what is still to do (reader serial, connect, test page)."""
    models = HARDWARE_MODELS.get(device.type, {})
    if model not in models:
        raise AppError("bad_model", f"For a {device.type} choose one of: {', '.join(models) or 'none'}")
    spec = models[model]
    to_do: list[str] = []
    printer = None
    builtin = await uow.session.scalar(
        select(Printer).where(Printer.device_id == device.id, Printer.name.like("% built-in printer"))
    )
    if spec.get("printer") or spec.get("kitchen_printer"):
        roles = ["kitchen"] if spec.get("kitchen_printer") else ["receipt", "token"]
        printer = builtin or Printer(
            venue_id=venue.id,
            name=f"{device.name} built-in printer",
            connection="screen",
            device_id=device.id,
            roles=roles,
            stations=[device.station] if spec.get("kitchen_printer") and device.station else [],
            paper_mm=80,
            last_status={},
        )
        printer.cash_drawer = bool(spec.get("cash_drawer"))
        printer.is_active = True
        uow.session.add(printer)
        if printer.tested_at is None:
            to_do.append("Connect the printer on the screen, then print the test page")
    elif builtin is not None:
        builtin.is_active = False  # the new model has no printer
    settings = dict(device.settings or {})
    if spec.get("card_reader"):
        serial = (terminal_id or (settings.get("card") or {}).get("terminal_id") or "").strip()
        if serial:
            settings["card"] = {"mode": "reader", "terminal_id": serial}
            to_do.append("Test the card reader")
        else:
            to_do.append("Type the card reader's serial number")
    settings["hardware"] = {
        "model": model,
        "name": spec["name"],
        **{
            k: bool(spec.get(k))
            for k in ("printer", "card_reader", "scanner", "cash_drawer", "customer_display")
        },
    }
    device.settings = settings
    await uow.session.flush()
    uow.audit(actor, "device.hardware", device.id, model=model)
    return {
        "model": model,
        "name": spec["name"],
        "printer_id": printer.id if printer else None,
        "to_do": to_do,
    }


# ------------------------------------------------------------------ equipment (install plan)

MANUAL_HARDWARE = ("router", "ups")  # the installer confirms these on site; the rest is counted


async def equipment(uow: UnitOfWork, venue: Venue) -> list[dict[str, Any]]:
    """Each piece of equipment: how many the package plans (at least what the screens need), and
    how many are installed. Printers, drawers and card readers are counted from the setup itself."""
    devices = (
        await uow.session.scalars(select(Device).where(Device.venue_id == venue.id, Device.is_active))
    ).all()
    types = {d.id: d.type for d in devices}
    counts: dict[str, int] = {}
    for d in devices:
        counts[d.type] = counts.get(d.type, 0) + 1
    planned = dict((venue.plan or {}).get("hardware") or {})
    reasons: dict[str, list[str]] = {}
    for item, (minimum, why) in requirements({**counts, **((venue.plan or {}).get("screens") or {})}).items():
        if item in HARDWARE:
            planned[item] = max(planned.get(item, 0), minimum)
            reasons[item] = why
    printers = (
        await uow.session.scalars(select(Printer).where(Printer.venue_id == venue.id, Printer.is_active))
    ).all()
    on_kiosk = [p for p in printers if types.get(p.device_id or "") == "kiosk"]
    confirmed = venue.setting("installed_hardware") or {}
    installed = {
        "receipt_printer": sum("receipt" in p.roles for p in printers if p not in on_kiosk),
        "kiosk_printer": len(on_kiosk),
        "kitchen_printer": sum("kitchen" in p.roles for p in printers),
        "cash_drawer": sum(p.cash_drawer for p in printers),
        "card_reader": sum(1 for d in devices if (card_setup(d) or {}).get("mode") == "reader"),
        "scanner": sum(1 for d in devices if ((d.settings or {}).get("hardware") or {}).get("scanner")),
        "hub": 1 if (await hybrid.status_row(uow, venue.id) or HubStatus()).registered_at else 0,
        **{k: int(confirmed.get(k, 0)) for k in MANUAL_HARDWARE},
    }
    return [
        {
            "item": item,
            "name": HARDWARE[item],
            "planned": planned.get(item, 0),
            "installed": installed.get(item, 0),
            "manual": item in MANUAL_HARDWARE,
            "required_because": reasons.get(item, []),
        }
        for item in HARDWARE
        if planned.get(item) or installed.get(item)
    ]


async def confirm_hardware(uow: UnitOfWork, venue: Venue, actor: Actor, item: str, count: int) -> None:
    if item not in MANUAL_HARDWARE:
        raise AppError("counted_automatically", f"{HARDWARE.get(item, item)} is counted from the setup")
    done = {**(venue.setting("installed_hardware") or {}), item: max(0, min(count, 50))}
    venue.settings = {**(venue.settings or {}), "installed_hardware": done}
    uow.audit(actor, "equipment.installed", venue.id, item=item, count=done[item])


# ------------------------------------------------------------------ go-live checklist


def _item(key: str, title: str, done: bool, detail: str, where: str) -> dict[str, Any]:
    return {"key": key, "title": title, "done": done, "detail": detail, "where": where}


async def checklist(uow: UnitOfWork, venue: Venue) -> dict[str, Any]:
    s = uow.session
    items = int(
        await s.scalar(
            select(func.count())
            .select_from(MenuItem)
            .where(MenuItem.venue_id == venue.id, MenuItem.is_active, MenuItem.price > 0)
        )
        or 0
    )
    taxes = int(
        await s.scalar(
            select(func.count()).select_from(TaxRule).where(TaxRule.venue_id == venue.id, TaxRule.is_active)
        )
        or 0
    )
    staff = (await s.scalars(select(Staff).where(Staff.venue_id == venue.id, Staff.is_active))).all()
    devices = (await s.scalars(select(Device).where(Device.venue_id == venue.id, Device.is_active))).all()
    online = hub.connected_devices(venue.id)
    unpaired = [d.name for d in devices if d.token_hash is None]
    offline = [d.name for d in devices if d.token_hash is not None and d.id not in online]
    pay = await payment_overview(uow, venue)
    printers = (await s.scalars(select(Printer).where(Printer.venue_id == venue.id, Printer.is_active))).all()
    untested = [p.name for p in printers if p.tested_at is None]
    tested = [p for p in printers if p.tested_at]

    def prints_for(device_id: str, roles: tuple[str, ...]) -> bool:
        """A tested printer of that screen, or a tested shared one, prints its slips."""
        return any(set(roles) & set(p.roles) and p.device_id in (device_id, None) for p in tested)

    tills = [d for d in devices if d.type == "cashier"]
    has_counter = bool(tills)
    tills_without = [d.name for d in tills if not prints_for(d.id, ("receipt",))]
    receipt_ok = not tills_without
    kitchen_needed = bool(venue.setting("print_kitchen_backup"))
    kitchen_ok = any("kitchen" in p.roles and p.tested_at for p in printers)
    paid = int(
        await s.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.venue_id == venue.id, Order.payment_status == "paid")
        )
        or 0
    )

    lq = pay["lankaqr"]
    kiosks = [d for d in devices if d.type == "kiosk"]
    readers = {c["device_id"]: c for c in pay["card_screens"]}
    qr_ok = pay["methods"]["lankaqr"] and lq["status"] == "ok"
    kiosk_gaps = []
    for k in kiosks:
        card_ok = pay["methods"]["card"] and bool(readers.get(k.id, {}).get("tested_at"))
        own_printer = any({"receipt", "token"} & set(p.roles) and p.device_id == k.id for p in tested)
        missing = [
            "" if k.token_hash else "not set up",
            "" if qr_ok or card_ok else "no tested way to pay here (QR payment or card reader)",
            "" if own_printer else "no tested printer for the order number",
        ]
        if any(missing):
            kiosk_gaps.append(f"{k.name}: {', '.join(x for x in missing if x)}")
    methods = pay["methods"]
    readers_untested = [c["name"] for c in pay["card_screens"] if not c["tested_at"]]
    roles = {x.role for x in staff}
    checks = [
        _item(
            "business",
            "Business details",
            bool(venue.setting("legal_name")),
            "Legal name, VAT number and receipt footer"
            if venue.setting("legal_name")
            else "Add the legal name (and VAT number if registered) for tax invoices",
            "Setup › Business details",
        ),
        _item(
            "menu",
            "Menu",
            items > 0,
            f"{items} items with prices" if items else "Add menu items with prices",
            "Menu",
        ),
        _item(
            "taxes",
            "Service charge and taxes",
            taxes > 0,
            f"{taxes} active rules" if taxes else "Add service charge / VAT / SSCL rules",
            "Menu › Taxes",
        ),
        _item(
            "staff",
            "Staff and PINs",
            "manager" in roles and len(staff) >= 2,
            f"{len(staff)} staff, manager {'set' if 'manager' in roles else 'missing'}",
            "Setup › Staff",
        ),
        _item(
            "screens",
            "Screens set up and online",
            bool(devices) and not unpaired and not offline,
            "All screens online"
            if devices and not unpaired and not offline
            else "; ".join(
                x
                for x in (
                    "No screens yet" if not devices else "",
                    f"Not set up: {', '.join(unpaired[:6])}" if unpaired else "",
                    f"Offline: {', '.join(offline[:6])}" if offline else "",
                )
                if x
            ),
            "Setup › Screens",
        ),
        _item(
            "payments",
            "Payments",
            any(methods.values()) and (not methods["lankaqr"] or lq["status"] == "ok"),
            "QR payment tested"
            if methods["lankaqr"] and lq["status"] == "ok"
            else "QR payment off"
            if not methods["lankaqr"]
            else "Enter the QR payment merchant details and press Test connection"
            if lq["status"] in ("not_set", "not_tested")
            else f"LankaQR test failed: {lq.get('last_error')}",
            "Setup › Payments",
        ),
        _item(
            "card_readers",
            "Card readers",
            not readers_untested,
            "No card readers"
            if not pay["card_screens"]
            else ("All readers tested" if not readers_untested else f"Test: {', '.join(readers_untested)}"),
            "Setup › Payments",
        ),
        _item(
            "printers",
            "Printers",
            (receipt_ok or not has_counter) and (kitchen_ok or not kitchen_needed) and not untested,
            "; ".join(
                x
                for x in (
                    f"No tested receipt printer for {', '.join(tills_without[:4])}"
                    if has_counter and not receipt_ok
                    else "",
                    "Kitchen backup is on: add a kitchen printer"
                    if kitchen_needed and not kitchen_ok
                    else "",
                    f"Print a test page on: {', '.join(untested)}" if untested else "",
                )
                if x
            )
            or "All printers tested",
            "Setup › Printers",
        ),
        _item(
            "kiosks",
            "Self-order kiosks",
            not kiosk_gaps,
            "No kiosks"
            if not kiosks
            else "; ".join(kiosk_gaps[:4]) or f"{len(kiosks)} kiosks: pay and print tested",
            "Setup › Payments / Printers",
        ),
        _item(
            "test_order",
            "One real test order",
            paid > 0,
            f"{paid} paid orders" if paid else "Order, pay, cook and hand over one order end to end",
            "Any screen",
        ),
    ]
    if venue.setting("network_mode") == "hybrid":
        net = await hybrid.network(uow, venue)
        box = net["hub"]
        checks.insert(
            5,
            _item(
                "network",
                "Hub online (Hybrid)",
                bool(box and box["alive"]),
                "Hub in charge, syncing with the cloud"
                if box and box["alive"]
                else "Connect the hub: Network › Hub setup code"
                if not box
                else "Hub not heard from: check its power and network",
                "Setup › Network",
            ),
        )
    kit = await equipment(uow, venue)
    short = [f"{e['name']} {e['installed']}/{e['planned']}" for e in kit if e["installed"] < e["planned"]]
    checks.insert(
        4,
        _item(
            "equipment",
            "Equipment installed",
            not short,
            "; ".join(short[:5]) or f"All {len(kit)} kinds of equipment in place",
            "Setup › Equipment",
        ),
    )
    done = sum(c["done"] for c in checks)
    return {"ready": done == len(checks), "done": done, "total": len(checks), "items": checks}
