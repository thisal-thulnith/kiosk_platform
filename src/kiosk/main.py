import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from kiosk.api.routers import (
    admin_menu,
    admin_org,
    ai,
    auth,
    demo,
    feedback,
    health,
    inventory,
    kds,
    ledger,
    loyalty,
    media,
    menu,
    orders,
    payments,
    platform,
    pos,
    receipts,
    reports,
    service,
    setup,
    shifts,
    sync,
    tables,
    ws,
)
from kiosk.config import settings
from kiosk.errors import NotFound, install_handlers
from kiosk.infra.db import init_db
from kiosk.jobs import expire_loop
from kiosk.sync import edge

log = structlog.get_logger()
UI_DIR = Path(__file__).parent / "web" / "ui"  # the React build (frontend/ -> npm run build)
# Clean addresses: /{restaurant code}/{screen}. The name in the address -> the built page.
PAGES = {
    "pos": "pos",
    "waiter": "waiter",
    "kitchen": "kds",
    "kiosk": "kiosk",
    "board": "status",
    "owner": "owner",
    "menu": "menu",
    "setup": "setup",
    "wall": "wall",
    "table": "table",
}
# Pages that open on the admin address: the Owner app, Menu editor and our Setup console.
ADMIN_PAGES = {"setup", "menu", "owner"}
# Old addresses (installed apps, printed QR codes, bookmarks) -> the new ones.
LEGACY_PAGES = {
    "app": "",
    "index": "setup",
    "platform": "platform",
    "owner": "owner",
    "menu": "menu",
    "cashier": "pos",
    "pos": "pos",
    "waiter": "waiter",
    "kds": "kitchen",
    "kiosk": "kiosk",
    "status": "board",
    "wall": "wall",
    "table": "table",
    "board": "table",
    "setup": "setup",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.run_background_jobs:
        tasks.append(asyncio.create_task(expire_loop(stop)))
        if settings.is_edge:
            tasks.append(asyncio.create_task(edge.run_forever(stop)))
    log.info("startup", mode=settings.app_mode, env=settings.env)
    yield
    stop.set()
    for t in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(t, timeout=5)


def create_app() -> FastAPI:
    init_db(settings.database_url)
    app = FastAPI(
        # Interactive API docs only outside production: in prod every URL needs a key.
        docs_url=None if settings.env == "prod" else "/docs",
        redoc_url=None if settings.env == "prod" else "/redoc",
        openapi_url=None if settings.env == "prod" else "/openapi.json",
        title=f"AI Hospitality Kiosk Platform ({settings.app_mode})",
        version="0.1.0",
        description="Order engine, KDS, payments and sync for restaurant kiosks. "
        "All money values are integer LKR cents.",
        lifespan=lifespan,
    )
    install_handlers(app)
    # A screen page served by the restaurant's hub falls back to the cloud API (and back): allow the
    # other origin. Auth is by header (device key / bearer), never by cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (
        health,
        auth,
        platform,
        admin_org,
        admin_menu,
        ai,
        inventory,
        ledger,
        feedback,
        loyalty,
        media,
        reports,
        receipts,
        menu,
        orders,
        payments,
        service,
        shifts,
        tables,
        kds,
        ws,
        sync,
        demo,
    ):
        app.include_router(r.router)
    app.include_router(admin_org.venues_router)
    app.include_router(setup.admin_router)
    app.include_router(setup.router)
    app.include_router(pos.router)
    app.include_router(pos.admin_router)

    def page(name: str) -> FileResponse:
        file = UI_DIR / name / "index.html"
        if not file.exists():
            raise NotFound("Page (build the screens: cd frontend && npm run build)")
        return FileResponse(file, headers={"Cache-Control": "no-cache"})

    def keep_query(request: Request) -> str:
        return f"?{request.url.query}" if request.url.query else ""

    # Old addresses (installed apps, printed QR codes, bookmarks) open the new ones.
    @app.get("/screens/", include_in_schema=False)
    @app.get("/screens/{old}.html", include_in_schema=False)
    @app.get("/screens/ui/{old}/", include_in_schema=False)
    async def old_page(request: Request, old: str = "app") -> RedirectResponse:
        target = LEGACY_PAGES.get(old)
        if target is None:
            raise NotFound("Page")
        return RedirectResponse(f"/{target}{keep_query(request)}")

    # The React build's files (scripts, styles, icons).
    app.mount("/static", StaticFiles(directory=UI_DIR, check_dir=False), name="static")
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    # The offline worker must sit at the root to look after every page.
    @app.get("/sw.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            UI_DIR / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest() -> FileResponse:
        return FileResponse(UI_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    # Our team's consoles live on their own address (ADMIN_HOST, e.g. admin.example.com).
    def on_admin(request: Request) -> bool:
        return bool(settings.admin_host) and request.url.hostname == settings.admin_host

    def to_admin(request: Request) -> RedirectResponse:
        return RedirectResponse(f"https://{settings.admin_host}{request.url.path}{keep_query(request)}")

    def to_app(request: Request) -> RedirectResponse:
        base = (settings.public_url or "").rstrip("/")
        return RedirectResponse(f"{base}{request.url.path}{keep_query(request)}")

    @app.middleware("http")
    async def team_login_on_admin_only(request: Request, call_next: Any) -> Any:
        """The team (platform) API answers only on the admin address, when there is one."""
        if settings.admin_host and request.url.path.startswith("/v1/platform") and not on_admin(request):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found"}}, status_code=404)
        return await call_next(request)

    # Pages: the tablet start page, our team's console, then each restaurant's screens and consoles.
    @app.get("/", include_in_schema=False)
    async def start(request: Request) -> Response:
        if settings.demo_mode:
            return RedirectResponse("/try")  # the public demo: every screen one tap away
        return page("platform") if on_admin(request) else page("app")

    @app.get("/try", include_in_schema=False)
    async def try_demo() -> Response:
        if not settings.demo_mode:
            raise NotFound("Page")
        return page("try")

    @app.get("/platform", include_in_schema=False)
    async def platform_console(request: Request) -> Response:
        if settings.admin_host and not on_admin(request):
            return to_admin(request)
        return page("platform")

    @app.get("/{screen}", include_in_schema=False)
    async def screen_without_code(request: Request, screen: str) -> Response:
        """/pos, /kitchen…: a set-up screen knows its restaurant and adds the code to the address.
        /demo (a restaurant's own address): its sign-in page, where a device types its screen code."""
        if screen in ADMIN_PAGES and settings.admin_host and not on_admin(request):
            return to_admin(request)
        if on_admin(request) and screen not in ADMIN_PAGES:
            return to_app(request)  # restaurants' screens live on the main address
        if screen in PAGES:
            return page(PAGES[screen])
        if screen.replace("-", "").isalnum() and len(screen) <= 20:
            return page("app")
        raise NotFound("Page")

    @app.get("/{code}/{screen}", include_in_schema=False)
    async def restaurant_page(request: Request, code: str, screen: str) -> Response:
        if screen not in PAGES or not code.replace("-", "").isalnum():
            raise NotFound("Page")
        if settings.admin_host:
            if screen in ADMIN_PAGES and not on_admin(request):
                return to_admin(request)  # owners, managers and our team: the admin address
            if screen not in ADMIN_PAGES and on_admin(request):
                return to_app(request)
        return page(PAGES[screen])

    return app


app = create_app()
