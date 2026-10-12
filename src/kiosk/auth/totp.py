"""Phone codes for 2-step login (TOTP, RFC 6238): Google Authenticator, Microsoft Authenticator,
1Password… show a new 6-digit code every 30 seconds from a secret shared once by QR code."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 10**DIGITS:0{DIGITS}d}"


def code_now(secret: str, at: float | None = None) -> str:
    return _code(secret, int((time.time() if at is None else at) // STEP))


def verify(secret: str, code: str, last_step: int | None = None) -> int | None:
    """The time step the code belongs to (now, or one step either side for clock drift), or None.
    A code already used (step <= last_step) is refused, so an overheard code can't be replayed."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = int(time.time() // STEP)
    for step in (now, now - 1, now + 1):
        if (last_step is None or step > last_step) and hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def setup_uri(secret: str, account: str, issuer: str) -> str:
    """What the QR code holds: authenticator apps add the account from it."""
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
