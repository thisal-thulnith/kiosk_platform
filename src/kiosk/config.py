from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["edge", "cloud"] = "edge"
    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite+aiosqlite:///./kiosk.db"
    jwt_secret: str = "dev-only-secret-change-me-in-production-000"
    staff_session_hours: int = 8
    admin_session_hours: int = 12
    # Our team's logins need a phone code (2-step). Default: on in prod, off in dev and tests.
    team_2fa: bool | None = None
    product_name: str = "Kiosk Platform"
    # A public demo server: /try opens every screen with one tap (never on a real restaurant's server).
    demo_mode: bool = False

    # Edge only: which venue this edge server belongs to, and how to reach the cloud.
    venue_id: str | None = None
    cloud_url: str | None = None
    cloud_sync_key: str | None = None
    sync_interval_seconds: float = 5.0

    # Payment gateway. "mock" signs callbacks with gateway_webhook_secret.
    gateway: Literal["mock"] = "mock"
    gateway_webhook_secret: str = "dev-webhook-secret"
    # Card terminals (built-in kiosk readers and SoftPOS / tap-on-tablet). "mock" simulates taps.
    card_terminal: Literal["mock"] = "mock"
    terminal_webhook_secret: str = "dev-terminal-secret"
    # Encrypts stored merchant keys (Fernet key; in dev one is derived from jwt_secret).
    data_key: str | None = None
    # Public address of this server, for URLs printed into printers' settings (CloudPRNT).
    public_url: str | None = None
    # Our team's address (Platform and Setup consoles), e.g. admin.example.com. When set, those
    # consoles and the team login open only there; restaurants use PUBLIC_URL.
    admin_host: str | None = None
    # Hub (edge mode): its address on the restaurant network, told to screens. Credentials from
    # `kiosk hub-setup` are kept in hub_file when not given as VENUE_ID / CLOUD_SYNC_KEY.
    lan_url: str | None = None
    hub_file: str = "./hub.json"
    # Cloud: a hybrid venue's hub counts as down after this long without a heartbeat; its screens
    # may then use the cloud directly (backup mode).
    hub_timeout_seconds: int = 60
    # Browsers may call the API from these origins (a hub page falling back to the cloud).
    cors_origins: str = "*"

    # Screens that are not offered yet ("Coming soon"): their screens show a coming-soon page and new
    # ones can't be added. Comma separated device types; empty switches everything on.
    coming_soon: str = "kiosk,status"

    run_background_jobs: bool = True
    print_dir: str = "./prints"
    # Uploaded menu photos (served at /media). In the cloud, point this at mounted object storage.
    media_dir: str = "./media"
    # Send print jobs in the background so a slow or offline printer never delays a response.
    print_async: bool = True

    @property
    def coming_soon_types(self) -> set[str]:
        return {t.strip() for t in self.coming_soon.split(",") if t.strip()}

    @property
    def is_edge(self) -> bool:
        return self.app_mode == "edge"

    def load_hub_file(self) -> None:
        """A hub set up with `kiosk hub-setup` finds its cloud, venue and key in hub_file."""
        import json
        from pathlib import Path

        path = Path(self.hub_file)
        if self.is_edge and path.exists() and not (self.venue_id and self.cloud_sync_key):
            data = json.loads(path.read_text())
            self.cloud_url = self.cloud_url or data.get("cloud_url")
            self.venue_id = data.get("venue_id")
            self.cloud_sync_key = data.get("sync_key")

    @property
    def team_2fa_required(self) -> bool:
        return self.env == "prod" if self.team_2fa is None else self.team_2fa

    @property
    def is_dev(self) -> bool:
        return self.env != "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and (
        "dev-only" in s.jwt_secret
        or s.gateway_webhook_secret.startswith("dev")
        or s.terminal_webhook_secret.startswith("dev")
        or not s.data_key
    ):
        raise RuntimeError(
            "Set JWT_SECRET, GATEWAY_WEBHOOK_SECRET, TERMINAL_WEBHOOK_SECRET and DATA_KEY"
            " before running in prod"
        )
    return s


settings = get_settings()
settings.load_hub_file()
