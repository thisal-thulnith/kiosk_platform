from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.infra.models import AuditLog, Outbox
from kiosk.realtime.hub import hub

log = structlog.get_logger()


@dataclass
class Actor:
    venue_id: str
    device_id: str | None = None
    staff_id: str | None = None
    staff_role: str | None = None
    admin_id: str | None = None
    platform_id: str | None = None  # our installer / support team, working on a client's venue


@dataclass
class _Pending:
    venue_id: str
    type: str
    data: dict[str, Any]
    topics: list[str]


@dataclass
class UnitOfWork:
    """A DB session plus the real-time events to publish once the transaction commits.

    Events are only published after a successful commit, so devices never see a change
    that was rolled back.
    """

    session: AsyncSession
    _events: list[_Pending] = field(default_factory=list)
    after_commit: list[Any] = field(default_factory=list)
    printed: list[str] = field(default_factory=list)  # printers this request printed on (names)

    def emit(self, venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> None:
        self._events.append(_Pending(venue_id, type_, data, topics))

    def outbox(self, venue_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.session.add(Outbox(venue_id=venue_id, kind=kind, payload=payload))

    def audit(self, actor: Actor, action: str, target: str | None = None, **data: Any) -> None:
        self.session.add(
            AuditLog(
                venue_id=actor.venue_id,
                action=action,
                target=target,
                data={**data, "platform_user": actor.platform_id} if actor.platform_id else data,
                device_id=actor.device_id,
                staff_id=actor.staff_id,
                admin_id=actor.admin_id,
            )
        )

    async def commit(self) -> None:
        await self.session.commit()
        events, self._events = self._events, []
        for e in events:
            await hub.publish(e.venue_id, e.type, e.data, e.topics)
        callbacks, self.after_commit = self.after_commit, []
        for cb in callbacks:
            try:
                await cb()
            except Exception:  # noqa: BLE001 - side effects (printing) must not fail a commit
                log.exception("after_commit.failed")
