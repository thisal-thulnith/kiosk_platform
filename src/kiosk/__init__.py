import argparse
import asyncio
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="kiosk", description="AI Hospitality Kiosk Platform")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    sub.add_parser("initdb", help="Create tables directly (dev). Use Alembic in production")
    sub.add_parser("seed", help="Load the demo café and a dev platform login")
    pa = sub.add_parser("create-platform-admin", help="Create a platform operator login")
    pa.add_argument("--email", required=True)
    pa.add_argument("--password", required=True)
    pa.add_argument("--name", default="")
    hs = sub.add_parser("hub-setup", help="On the restaurant's hub box: connect it to the cloud (once)")
    hs.add_argument("--cloud", required=True, help="Cloud address, e.g. https://cloud.example.lk")
    hs.add_argument("--code", required=True, help="Hub setup code from the Setup console")
    hs.add_argument(
        "--lan-url", default=None, help="This box on the restaurant network, e.g. http://192.168.1.20:8000"
    )
    args = parser.parse_args()

    if args.cmd == "serve":
        import uvicorn

        os.environ.setdefault("KIOSK_PORT", str(args.port))  # the hub tells screens its address
        uvicorn.run("kiosk.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "initdb":
        asyncio.run(_initdb())
    elif args.cmd == "seed":
        asyncio.run(_seed())
    elif args.cmd == "hub-setup":
        _hub_setup(args.cloud, args.code, args.lan_url)
    elif args.cmd == "create-platform-admin":
        if len(args.password) < 10:
            parser.error("password must be at least 10 characters")
        asyncio.run(_platform_admin(args.email, args.password, args.name))


def _hub_setup(cloud: str, code: str, lan_url: str | None) -> None:
    """Trade the one-time code for the venue's sync key and keep it in hub_file (chmod 600)."""
    import os
    from pathlib import Path

    import httpx

    from kiosk.config import settings

    r = httpx.post(
        f"{cloud.rstrip('/')}/v1/sync/register", json={"code": code, "lan_url": lan_url}, timeout=15
    )
    if r.status_code != 200:
        raise SystemExit(f"Hub setup failed: {r.text}")
    data = r.json()
    path = Path(settings.hub_file)
    path.write_text(
        json.dumps(
            {"cloud_url": cloud.rstrip("/"), "venue_id": data["venue_id"], "sync_key": data["sync_key"]}
        )
    )
    os.chmod(path, 0o600)
    print(
        f"Hub connected to {data['venue_name']}. Start it with: "
        f"APP_MODE=edge LAN_URL={lan_url or '<this box>'} kiosk serve"
    )


async def _initdb() -> None:
    from kiosk.config import settings
    from kiosk.infra.db import create_all, init_db

    init_db(settings.database_url)
    await create_all()
    print("Tables created")


async def _seed() -> None:
    from kiosk.config import settings
    from kiosk.infra.db import init_db, session_factory
    from kiosk.seed import seed

    init_db(settings.database_url)
    async with session_factory()() as session:
        result = await seed(session)
        await session.commit()
    print(json.dumps(result, indent=2, ensure_ascii=False))


async def _platform_admin(email: str, password: str, name: str) -> None:
    from kiosk.config import settings
    from kiosk.infra.db import init_db, session_factory
    from kiosk.seed import ensure_platform_admin

    init_db(settings.database_url)
    async with session_factory()() as session:
        created = await ensure_platform_admin(session, email, password, name)
        await session.commit()
    print("Platform admin created" if created else "That email already has a platform login")
