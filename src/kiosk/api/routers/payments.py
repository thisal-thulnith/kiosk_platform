from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from kiosk.api.deps import Uow
from kiosk.config import settings
from kiosk.errors import AppError, NotFound, Unauthorized
from kiosk.infra.gateway import InvalidSignature, get_gateway
from kiosk.infra.models import Order, Payment
from kiosk.infra.terminal import get_terminal
from kiosk.services import payments as pay
from kiosk.services.serializers import order_dict

router = APIRouter(prefix="/v1", tags=["payments"])


@router.post("/payments/gateway/callback")
async def gateway_callback(
    request: Request, uow: Uow, x_signature: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """Called by the payment gateway. Signed with HMAC-SHA256 over the raw body."""
    body = await request.body()
    try:
        data = get_gateway().verify_callback(body, x_signature or "")
    except InvalidSignature as exc:
        raise Unauthorized("Bad gateway signature") from exc
    result = await pay.receive_callback(uow, "gateway.callback", data)
    await uow.commit()
    return result


@router.post("/payments/terminal/callback")
async def terminal_callback(
    request: Request, uow: Uow, x_signature: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """Called by the card processor after a tap/chip payment on a reader or SoftPOS tablet."""
    body = await request.body()
    try:
        data = get_terminal().verify_callback(body, x_signature or "")
    except InvalidSignature as exc:
        raise Unauthorized("Bad terminal signature") from exc
    result = await pay.receive_callback(uow, "terminal.callback", data)
    await uow.commit()
    return result


@router.post("/dev/mock-terminal/{terminal_ref}/{outcome}", tags=["dev"])
async def mock_terminal_tap(terminal_ref: str, outcome: str, uow: Uow) -> dict[str, Any]:
    """Dev only: pretend a card was tapped on the reader (outcome = succeeded | failed)."""
    if not settings.is_dev:
        raise NotFound("Endpoint")
    if outcome not in ("succeeded", "failed"):
        raise AppError("bad_outcome", "outcome must be succeeded or failed")
    payment = await uow.session.scalar(
        select(Payment).where(Payment.gateway_ref == terminal_ref, Payment.method == "card")
    )
    if payment is None:
        raise NotFound("Payment")
    body, sig = get_terminal().build_callback(terminal_ref, outcome, payment.amount)
    result = await pay.receive_callback(uow, "terminal.callback", get_terminal().verify_callback(body, sig))
    await uow.commit()
    return await _result(uow, result)


@router.post("/dev/mock-gateway/{gateway_ref}/{outcome}", tags=["dev"])
async def mock_gateway_pay(gateway_ref: str, outcome: str, uow: Uow) -> dict[str, Any]:
    """Dev only: pretend the guest scanned the QR and paid (outcome = succeeded | failed)."""
    if not settings.is_dev:
        raise NotFound("Endpoint")
    if outcome not in ("succeeded", "failed"):
        raise AppError("bad_outcome", "outcome must be succeeded or failed")
    payment = await uow.session.scalar(select(Payment).where(Payment.gateway_ref == gateway_ref))
    if payment is None:
        raise NotFound("Payment")
    body, sig = get_gateway().build_callback(gateway_ref, outcome, payment.amount)
    data = get_gateway().verify_callback(body, sig)
    result = await pay.receive_callback(uow, "gateway.callback", data)
    await uow.commit()
    return await _result(uow, result)


async def _result(uow: Uow, result: dict[str, Any]) -> dict[str, Any]:
    """Dev helpers answer with the order, or say the result went on to the restaurant's hub."""
    if result.get("forwarded_to_hub"):
        return result
    order = await uow.session.get(Order, result["order_id"])
    assert order is not None
    await uow.session.refresh(order)
    return order_dict(order)
