"""Screen codes, like Square device codes: each screen (table, POS, waiter, kitchen) has its own
code. The restaurant's address + the code sign a device in for good. A code only works at its own
restaurant and for its own screen; signing in again on another tablet signs the old one out;
resetting the code signs the device out too."""

import secrets

from sqlalchemy import select

from kiosk.auth.security import token_digest
from kiosk.infra.models import Device
from kiosk.infra.secrets import decrypt, encrypt
from kiosk.services.uow import UnitOfWork

# No look-alikes (0/O, 1/I/L), so codes can be read out over the phone and typed without mistakes.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LENGTH = 10  # 31^10 ≈ 8 × 10^14 codes, and wrong guesses are rate-limited


def normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def pretty(code: str) -> str:
    c = normalize(code)
    return f"{c[:4]}-{c[4:8]}-{c[8:]}" if len(c) == LENGTH else c


def digest(code: str) -> str:
    return token_digest("screen:" + normalize(code))


def new_code(device: Device) -> str:
    """Give the screen a new code (the old one stops working). Returns it, formatted."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    device.code_hash = digest(code)
    device.code_enc = encrypt(code)
    return pretty(code)


def shown(device: Device) -> str | None:
    """The code as the Setup console shows it."""
    if not device.code_enc:
        return None
    plain = decrypt(device.code_enc)
    return pretty(plain) if plain else None


def ensure(device: Device) -> str:
    return shown(device) or new_code(device)


async def find(uow: UnitOfWork, code: str) -> Device | None:
    c = normalize(code)
    if len(c) != LENGTH:
        return None
    return await uow.session.scalar(select(Device).where(Device.code_hash == digest(c)))
