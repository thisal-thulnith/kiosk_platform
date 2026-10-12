from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from kiosk.api.deps import load_device
from kiosk.errors import AppError
from kiosk.infra.db import session_factory
from kiosk.infra.models import Venue, utcnow
from kiosk.realtime.hub import Connection, hub
from kiosk.services import hybrid
from kiosk.services.uow import UnitOfWork

router = APIRouter(tags=["realtime"])

DEFAULT_TOPICS = {
    "cashier": {"orders", "menu", "status"},
    "kds": {"kds", "menu"},
    "status": {"status"},
    "kiosk": {"menu", "status", "service"},
    "table": {"menu", "status", "orders", "service"},
    "waiter": {"orders", "menu", "status", "service"},
    "board": {"menu", "status"},
}


@router.websocket("/v1/ws")
async def ws(
    websocket: WebSocket,
    token: str = Query(..., description="Device token"),
    since: int | None = Query(None, description="Last seq received, to replay missed events"),
    epoch: str | None = Query(None, description="Hub epoch from the last hello message"),
    topics: str | None = Query(None, description="Comma separated; defaults by device type"),
) -> None:
    """Real-time events. First message is {"type": "hello", "epoch", "seq"}.

    If you get {"type": "resync"}, reload state from the REST endpoints.
    Send {"type": "ping"} to keep the connection alive; the server answers "pong".
    """
    async with session_factory()() as session:
        try:
            device = await load_device(session, token)
        except AppError:
            await websocket.close(code=4401)
            return
        device.last_seen_at = utcnow()
        venue = await session.get(Venue, device.venue_id)
        use_hub = venue is not None and await hybrid.hub_in_charge(UnitOfWork(session), venue)
        await session.commit()
    if use_hub:
        await websocket.close(code=4409)  # the restaurant's hub is running: connect to the hub
        return

    wanted = set(topics.split(",")) if topics else set(DEFAULT_TOPICS.get(device.type, {"all"}))
    if device.type == "kds" and device.station and not topics:
        wanted = {f"kds:{device.station}", "menu"}
    wanted.add(f"device:{device.id}")  # remote commands for this screen (reload, identify)
    await websocket.accept()
    conn = Connection(websocket, device.venue_id, device.id, wanted)
    await hub.connect(conn, since, epoch)
    try:
        while True:
            msg = await websocket.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "seq": hub.last_seq(device.venue_id)})
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(conn)
