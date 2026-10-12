from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.infra.models import Counter


async def next_value(session: AsyncSession, venue_id: str, key: str) -> int:
    """Atomically increment a counter inside the caller's transaction.

    The increment rolls back with the transaction, so sequences stay gapless.
    """
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = (
        insert(Counter)
        .values(venue_id=venue_id, key=key, value=1)
        .on_conflict_do_update(
            index_elements=[Counter.venue_id, Counter.key],
            set_={"value": Counter.value + 1},
        )
        .returning(Counter.value)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def peek(session: AsyncSession, venue_id: str, key: str) -> int:
    value = await session.scalar(
        select(Counter.value).where(Counter.venue_id == venue_id, Counter.key == key)
    )
    return int(value or 0)
