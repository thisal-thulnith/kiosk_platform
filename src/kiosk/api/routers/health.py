from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from kiosk.api.deps import Uow
from kiosk.config import settings
from kiosk.infra.models import utcnow
from kiosk.sync.state import state

router = APIRouter(tags=["health"])


@router.get("/v1/health")
async def health(uow: Uow) -> dict[str, Any]:
    await uow.session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "mode": settings.app_mode,
        "time": utcnow().isoformat(),
        "cloud_online": state.cloud_online if settings.is_edge else None,
    }


@router.get("/v1/features")
async def features() -> dict[str, Any]:
    """What this server offers yet. Screens and consoles show "Coming soon" for the rest."""
    # demo: a development / test server, where the login pages may fill in the demo logins.
    return {
        "coming_soon": sorted(settings.coming_soon_types),
        "demo": settings.is_dev,
        # Where restaurants' screens live, and our team's consoles (links and QR codes use these).
        "app_url": settings.public_url,
        "admin_url": f"https://{settings.admin_host}" if settings.admin_host else None,
    }
