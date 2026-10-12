"""Payment gateway adapters.

Only a mock gateway exists for now. A real LankaQR adapter (from the bank or gateway
partner) must implement the same three methods. The gateway's signed callback is the
source of truth for whether a QR payment succeeded.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol

from ulid import ULID

from kiosk.config import settings


@dataclass(frozen=True)
class QrRequest:
    gateway_ref: str
    qr_payload: str


class Gateway(Protocol):
    async def create_qr(self, order_id: str, amount: int, reference: str) -> QrRequest: ...

    async def refund(self, gateway_ref: str, amount: int) -> str: ...

    def verify_callback(self, body: bytes, signature: str) -> dict[str, Any]: ...

    async def check(self, merchant_id: str, secret: str | None, live: bool) -> None:
        """Log in to the provider with the venue's merchant details. Raises GatewayError."""
        ...


class InvalidSignature(Exception):
    pass


class GatewayError(Exception):
    pass


PROVIDERS = {
    # code: (name shown at setup, what it needs). A bank's integration kit adds its own entry.
    "mock": ("Test gateway (no real money)", ["merchant_id"]),
}


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class MockGateway:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def create_qr(self, order_id: str, amount: int, reference: str) -> QrRequest:
        ref = f"MOCK-{ULID()}"
        # Real LankaQR payloads are EMVCo strings from the gateway; this is a stand-in.
        return QrRequest(ref, f"LANKAQR|MOCK|{ref}|{reference}|LKR|{amount / 100:.2f}")

    async def refund(self, gateway_ref: str, amount: int) -> str:
        return f"MOCKREFUND-{ULID()}"

    async def check(self, merchant_id: str, secret: str | None, live: bool) -> None:
        if not merchant_id:
            raise GatewayError("Merchant ID is missing")
        if secret == "wrong-key":  # lets installers and tests see what a failed check looks like
            raise GatewayError("The gateway refused the API key")

    def verify_callback(self, body: bytes, signature: str) -> dict[str, Any]:
        if not hmac.compare_digest(sign(body, self.secret), signature):
            raise InvalidSignature("bad signature")
        data: dict[str, Any] = json.loads(body)
        return data

    def build_callback(self, gateway_ref: str, status: str, amount: int) -> tuple[bytes, str]:
        """Dev helper: what the gateway would POST to us."""
        body = json.dumps({"gateway_ref": gateway_ref, "status": status, "amount": amount}).encode()
        return body, sign(body, self.secret)


def get_gateway() -> MockGateway:
    return MockGateway(settings.gateway_webhook_secret)
