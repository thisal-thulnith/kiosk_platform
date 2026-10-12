from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_db(url: str) -> AsyncEngine:
    global _engine, _sessionmaker
    kwargs: dict[str, object] = {}
    if url.startswith("sqlite"):
        # A fresh connection per session keeps aiosqlite safe across event loops (tests, CLI).
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_pre_ping"] = True
    _engine = create_async_engine(url, **kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("init_db() has not been called")
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_db() has not been called")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


async def create_all() -> None:
    from kiosk.infra.models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
