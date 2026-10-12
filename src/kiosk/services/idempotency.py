"""Idempotency keys: a device that retries a write gets the first response back.

The key is stored in the same transaction as the write it protects.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.infra.models import IdempotencyKey


async def lookup(session: AsyncSession, scope: str, key: str | None) -> IdempotencyKey | None:
    if not key:
        return None
    found: IdempotencyKey | None = await session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
    )
    return found


def remember(
    session: AsyncSession, scope: str, key: str | None, status_code: int, response: dict[str, Any]
) -> None:
    if key:
        session.add(IdempotencyKey(scope=scope, key=key, status_code=status_code, response=response))
