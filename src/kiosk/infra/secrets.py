"""Encryption at rest for merchant keys (Fernet: AES-128-CBC + HMAC-SHA256)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from kiosk.config import settings


def _fernet() -> Fernet:
    if settings.data_key:
        return Fernet(settings.data_key.encode())
    # Dev / test only (prod refuses to start without DATA_KEY): derive a stable key.
    digest = hashlib.sha256(f"data-key:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
