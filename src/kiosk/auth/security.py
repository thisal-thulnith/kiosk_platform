import hashlib
import secrets
from datetime import timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from kiosk.config import settings
from kiosk.errors import Unauthorized
from kiosk.infra.models import utcnow

_hasher = PasswordHash.recommended()  # Argon2id


def hash_secret(value: str) -> str:
    """Slow hash for PINs and passwords."""
    return _hasher.hash(value)


def verify_secret(value: str, hashed: str) -> bool:
    return _hasher.verify(value, hashed)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Fast hash for high-entropy random tokens, so they can be looked up by index."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_jwt(claims: dict[str, Any], hours: int) -> str:
    now = utcnow()
    payload = {**claims, "iat": now, "exp": now + timedelta(hours=hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_jwt(token: str, typ: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid token") from exc
    if payload.get("typ") != typ:
        raise Unauthorized("Wrong token type")
    return payload
