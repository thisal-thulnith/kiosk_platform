from dataclasses import dataclass
from datetime import datetime

from kiosk.config import settings


@dataclass
class SyncState:
    cloud_online: bool = True
    last_push_at: datetime | None = None
    last_pull_at: datetime | None = None
    last_error: str | None = None
    pending: int = 0


state = SyncState()


def lankaqr_available() -> bool:
    """LankaQR needs the gateway callback, which needs the internet.

    A standalone edge (no cloud configured, e.g. dev) uses the mock gateway directly.
    """
    if not settings.is_edge or not settings.cloud_url:
        return True
    return state.cloud_online
