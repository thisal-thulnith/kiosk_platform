"""Edge <-> cloud sync with two separate databases and the real sync worker functions."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from kiosk.auth.security import token_digest
from kiosk.config import settings
from kiosk.infra.db import create_all, get_session, session_factory
from kiosk.infra.models import Base, Invoice, MenuItem, Order, Outbox, Staff, Venue
from kiosk.main import create_app
from kiosk.seed import seed
from kiosk.services import orders as order_svc
from kiosk.services import payments as pay
from kiosk.services.menu import CartLine
from kiosk.services.uow import Actor, UnitOfWork
from kiosk.sync import edge


async def test_config_pull_order_push_and_idempotent_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Edge DB is the app's global DB; the cloud gets its own engine.
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path}/edge.db")
    monkeypatch.setattr(settings, "print_dir", str(tmp_path / "prints"))
    cloud_app = create_app()
    await create_all()

    cloud_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/cloud.db", poolclass=NullPool)
    async with cloud_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    cloud = async_sessionmaker(cloud_engine, expire_on_commit=False)
    async with cloud() as s:
        info = await seed(s)
        venue = await s.get(Venue, info["venue_id"])
        assert venue
        venue.sync_key_hash = token_digest("secret-key")
        await s.commit()

    async def cloud_session() -> AsyncIterator[AsyncSession]:
        async with cloud() as s:
            yield s

    cloud_app.dependency_overrides[get_session] = cloud_session
    monkeypatch.setattr(settings, "app_mode", "cloud")  # the cloud app's sync endpoints check this
    monkeypatch.setattr(settings, "venue_id", info["venue_id"])
    monkeypatch.setattr(settings, "cloud_sync_key", "secret-key")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=cloud_app), base_url="http://cloud") as c:
        # 1. First pull creates the venue, staff and menu on the empty edge.
        assert await edge.pull_once(c) is True
        assert await edge.pull_once(c) is False  # nothing new
        async with session_factory()() as s:
            assert await s.scalar(select(func.count()).select_from(Staff)) == 4
            fries = await s.scalar(select(MenuItem).where(MenuItem.price == 45000))
            assert fries is not None
            fries_id = fries.id
            fries.is_available = False  # edge-owned stock switch
            other = await s.scalar(select(MenuItem).where(MenuItem.price == 35000))
            assert other
            juice_id = other.id
            await s.commit()

        # 2. An order taken at the edge while "offline" reaches the cloud later.
        async with session_factory()() as s:
            uow = UnitOfWork(s)
            v = await s.get(Venue, info["venue_id"])
            assert v
            actor = Actor(venue_id=v.id, device_id="dev1")
            order = await order_svc.create_order(uow, v, actor, "cashier", [CartLine(juice_id, 2)])
            await pay.pay_card(uow, v, order, actor, "APPROVAL-1")
            await uow.commit()
            order_id = order.id

        sent = await edge.push_once(c)
        assert sent >= 3
        async with cloud() as s:
            o = await s.get(Order, order_id)
            assert o and o.status == "in_kitchen" and o.payment_status == "paid"
            assert len(o.items) == 1 and len(o.payments) == 1
            assert await s.scalar(select(Invoice.number).where(Invoice.order_id == order_id))

        # 3. Re-sending everything (e.g. the ack was lost) changes nothing.
        async with session_factory()() as s:
            await s.execute(update(Outbox).values(sent_at=None))
            await s.commit()
        await edge.push_once(c)
        async with cloud() as s:
            assert await s.scalar(select(func.count()).select_from(Order)) == 1
            assert await s.scalar(select(func.count()).select_from(Invoice)) == 1

        # 4. A price change in the cloud reaches the edge; the local sold-out flag survives.
        async with cloud() as s:
            await s.execute(update(MenuItem).where(MenuItem.id == fries_id).values(price=50000))
            await s.execute(update(Venue).values(config_version=Venue.config_version + 1))
            await s.commit()
        assert await edge.pull_once(c) is True
        async with session_factory()() as s:
            fries = await s.get(MenuItem, fries_id)
            assert fries and fries.price == 50000 and fries.is_available is False

        # 5. Wrong key is refused.
        monkeypatch.setattr(settings, "cloud_sync_key", "wrong")
        with pytest.raises(httpx.HTTPStatusError):
            await edge.pull_once(c)
    await cloud_engine.dispose()
