"""Card terminal adapters: tap / chip card payments.

Two kinds of hardware, one interface:

  * reader  - a certified unattended reader built into a kiosk (e.g. PAX IM30), driven
              "semi-integrated": we send the amount, the reader talks to the bank.
  * softpos - the staff tablet's own NFC chip, through the bank's certified SoftPOS app or
              SDK (e.g. PAYableTAP). Card networks only allow this where staff are present,
              so it is never used on kiosks or table screens.

Card numbers never reach this system. The processor's signed callback is the source of truth
for whether a payment was approved, exactly like the LankaQR gateway. Only a mock exists; a
bank's integration kit must implement the same four methods.
"""

import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol

from ulid import ULID

from kiosk.config import settings
from kiosk.infra.gateway import InvalidSignature, sign


@dataclass(frozen=True)
class TerminalRequest:
    terminal_ref: str  # the processor's id for this payment attempt


class CardTerminal(Protocol):
    async def start(self, terminal_id: str, amount: int, reference: str) -> TerminalRequest: ...

    async def cancel(self, terminal_ref: str) -> None: ...

    async def ping(self, terminal_id: str) -> None:
        """Is the reader registered with the processor and online? Raises TerminalError."""
        ...

    async def refund(self, terminal_ref: str, amount: int) -> str: ...

    def verify_callback(self, body: bytes, signature: str) -> dict[str, Any]: ...


class TerminalError(Exception):
    pass


class MockTerminal:
    """Pretends to be a reader / SoftPOS processor. Use /v1/dev/mock-terminal to 'tap a card'."""

    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def start(self, terminal_id: str, amount: int, reference: str) -> TerminalRequest:
        return TerminalRequest(f"MOCKCARD-{ULID()}")

    async def cancel(self, terminal_ref: str) -> None:
        return None

    async def ping(self, terminal_id: str) -> None:
        if terminal_id.upper().startswith("OFFLINE"):
            raise TerminalError(f"Reader {terminal_id} is not online")

    async def refund(self, terminal_ref: str, amount: int) -> str:
        return f"MOCKCARDREFUND-{ULID()}"

    def verify_callback(self, body: bytes, signature: str) -> dict[str, Any]:
        if not hmac.compare_digest(sign(body, self.secret), signature):
            raise InvalidSignature("bad signature")
        data: dict[str, Any] = json.loads(body)
        return data

    def build_callback(self, terminal_ref: str, status: str, amount: int) -> tuple[bytes, str]:
        """Dev helper: what the processor would POST to us after the guest taps."""
        payload = {"terminal_ref": terminal_ref, "status": status, "amount": amount}
        if status == "succeeded":
            payload |= {"auth_code": f"A{str(ULID())[-6:]}", "card_brand": "VISA", "last4": "4242"}
        body = json.dumps(payload).encode()
        return body, sign(body, self.secret)


def get_terminal() -> MockTerminal:
    return MockTerminal(settings.terminal_webhook_secret)
