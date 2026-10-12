"""In-process real-time hub for the edge server.

Each venue has a monotonically increasing event sequence and a ring buffer of recent
events. A device that reconnects sends the last `seq` it saw (and the hub `epoch`) and
gets everything it missed. If the gap is too old, or the server restarted (new epoch),
it is told to resync from the REST snapshot endpoints instead.

Devices subscribe to topics: "orders", "kds", "kds:<station>", "status", "menu", "all".
"""

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import WebSocket
from ulid import ULID

from kiosk.infra.models import utcnow

log = structlog.get_logger()
BUFFER_SIZE = 2000


@dataclass
class Event:
    seq: int
    type: str
    topics: list[str]
    data: dict[str, Any]
    at: str

    def message(self, epoch: str) -> dict[str, Any]:
        return {"seq": self.seq, "epoch": epoch, "type": self.type, "data": self.data, "at": self.at}


@dataclass(eq=False)  # compared and hashed by identity, so it can live in a set
class Connection:
    ws: WebSocket
    venue_id: str
    device_id: str
    topics: set[str]

    def wants(self, event: Event) -> bool:
        return "all" in self.topics or any(t in self.topics for t in event.topics)


@dataclass
class _VenueStream:
    seq: int = 0
    buffer: deque[Event] = field(default_factory=lambda: deque(maxlen=BUFFER_SIZE))


class Hub:
    def __init__(self) -> None:
        self.epoch = str(ULID())
        self._streams: dict[str, _VenueStream] = {}
        self._conns: set[Connection] = set()
        self._lock = asyncio.Lock()

    def _stream(self, venue_id: str) -> _VenueStream:
        return self._streams.setdefault(venue_id, _VenueStream())

    def last_seq(self, venue_id: str) -> int:
        return self._stream(venue_id).seq

    async def publish(self, venue_id: str, type_: str, data: dict[str, Any], topics: list[str]) -> Event:
        async with self._lock:
            stream = self._stream(venue_id)
            stream.seq += 1
            event = Event(stream.seq, type_, topics, data, utcnow().isoformat())
            stream.buffer.append(event)
            targets = [c for c in self._conns if c.venue_id == venue_id and c.wants(event)]
        msg = event.message(self.epoch)
        await asyncio.gather(*(self._send(c, msg) for c in targets))
        return event

    async def _send(self, conn: Connection, msg: dict[str, Any]) -> None:
        try:
            await conn.ws.send_json(msg)
        except Exception:  # noqa: BLE001 - a dead socket must never break publishing
            self._conns.discard(conn)
            with contextlib.suppress(Exception):
                await conn.ws.close()

    async def connect(self, conn: Connection, since: int | None, epoch: str | None) -> None:
        async with self._lock:
            stream = self._stream(conn.venue_id)
            hello = {"type": "hello", "epoch": self.epoch, "seq": stream.seq}
            await conn.ws.send_json(hello)
            if since is not None:
                oldest = stream.buffer[0].seq if stream.buffer else stream.seq + 1
                too_old = since + 1 < oldest and since < stream.seq
                if epoch != self.epoch or too_old:
                    await conn.ws.send_json({"type": "resync", "epoch": self.epoch})
                else:
                    for event in stream.buffer:
                        if event.seq > since and conn.wants(event):
                            await conn.ws.send_json(event.message(self.epoch))
            self._conns.add(conn)
        log.info("ws.connected", device=conn.device_id, topics=sorted(conn.topics))

    def disconnect(self, conn: Connection) -> None:
        self._conns.discard(conn)

    def connected_devices(self, venue_id: str) -> set[str]:
        return {c.device_id for c in self._conns if c.venue_id == venue_id}


hub = Hub()
