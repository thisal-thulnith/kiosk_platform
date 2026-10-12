"""The receipt link a guest gets by text: a private URL (signed), no login."""

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from kiosk.api.deps import Uow
from kiosk.errors import NotFound
from kiosk.infra.models import Invoice, Order, Venue
from kiosk.services import printing, sms

router = APIRouter(prefix="/v1", tags=["receipts"])


@router.get("/receipts/{ref}", response_class=HTMLResponse)
async def receipt_page(ref: str, uow: Uow) -> HTMLResponse:
    order_id = sms.order_from_ref(ref)
    order = await uow.session.get(Order, order_id) if order_id else None
    venue = await uow.session.get(Venue, order.venue_id) if order else None
    if order is None or venue is None or order.payment_status not in ("paid", "refunded", "part_refunded"):
        raise NotFound("Receipt")
    inv = await uow.session.scalar(select(Invoice).where(Invoice.order_id == order.id))
    text = printing.render_receipt(venue, order, inv, drawer=False).text
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Receipt {html.escape(order.token)}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f6f3ef;margin:0;padding:16px}}
pre{{background:#fff;max-width:420px;margin:0 auto;padding:18px;border-radius:12px;
font:13px/1.45 ui-monospace,monospace;white-space:pre-wrap;box-shadow:0 4px 20px #0001}}</style></head>
<body><pre>{html.escape(text)}</pre></body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"})
