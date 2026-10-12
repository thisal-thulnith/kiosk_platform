import asyncio

import structlog

from kiosk.infra.db import session_factory
from kiosk.services import orders as order_svc
from kiosk.services import posbridge, sms
from kiosk.services.uow import UnitOfWork

log = structlog.get_logger()


async def expire_loop(stop: asyncio.Event, interval: float = 15.0) -> None:
    """Cancel unpaid "Pay at cashier" orders once their time runs out."""
    while not stop.is_set():
        try:
            async with session_factory()() as session:
                uow = UnitOfWork(session)
                expired = await order_svc.expire_due(uow)
                await uow.commit()
                await sms.retry_queued()  # texts that could not go out (e.g. hub without internet)
                await posbridge.retry_due()  # order events the restaurant's POS did not take yet
                if expired:
                    log.info("orders.expired", count=len(expired), tokens=[o.token for o in expired])
        except Exception:  # noqa: BLE001
            log.exception("expire_loop.failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
