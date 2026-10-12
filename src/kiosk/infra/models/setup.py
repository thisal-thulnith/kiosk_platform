"""Install-time setup: printers, the print queue, and each venue's payment accounts."""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kiosk.infra.models.base import Base, IdMixin, TimestampMixin

PRINTER_CONNECTIONS = ("cloud", "screen", "network", "file")
PRINT_ROLES = ("receipt", "token", "kitchen")


class Printer(IdMixin, TimestampMixin, Base):
    """A receipt or kitchen printer.

    connection:
      cloud  - the printer fetches its jobs from our cloud itself (Star CloudPRNT). No wiring to a
               screen and nothing on site; the printer's settings page gets one URL.
      screen - USB or Bluetooth printer plugged into a cashier / kitchen screen, which prints the
               jobs it is sent (WebUSB / Web Bluetooth in Chrome on Android and Windows).
      network - Ethernet / Wi-Fi printer on the restaurant's network (raw TCP, port 9100). The
               restaurant's hub sends it each job directly, so it keeps printing without internet
               (like Toast's local hub or Oracle's on-site CAPS). Needs a Hybrid restaurant.
      file   - testing only: jobs are written to files on the server.
    """

    __tablename__ = "printers"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    connection: Mapped[str] = mapped_column(String(20))
    roles: Mapped[list[Any]] = mapped_column(default=list)  # receipt | token | kitchen
    stations: Mapped[list[Any]] = mapped_column(default=list)  # kitchen tickets: empty = all stations
    device_id: Mapped[str | None] = mapped_column(String(26))  # connection "screen": the host screen
    host: Mapped[str | None] = mapped_column(String(120))  # connection "network": IP or name on the LAN
    port: Mapped[int] = mapped_column(default=9100)
    paper_mm: Mapped[int] = mapped_column(default=80)
    cash_drawer: Mapped[bool] = mapped_column(default=False)
    token_digest: Mapped[str | None] = mapped_column(String(64), unique=True)  # cloud poll URL secret
    token_enc: Mapped[str | None] = mapped_column(Text)  # the same secret, encrypted, to show the URL again
    is_active: Mapped[bool] = mapped_column(default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column()
    last_status: Mapped[dict[str, Any]] = mapped_column(default=dict)  # paper out, cover open...
    tested_at: Mapped[datetime | None] = mapped_column()  # the installer saw the test page print


class PrintJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "print_jobs"
    __table_args__ = (Index("ix_print_jobs_printer_status", "printer_id", "status"),)

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    printer_id: Mapped[str] = mapped_column(ForeignKey("printers.id"))
    label: Mapped[str] = mapped_column(String(80))
    escpos: Mapped[bytes] = mapped_column(LargeBinary)
    text: Mapped[str] = mapped_column(Text, default="")  # plain version for printers that take text
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | sent | done | failed
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(300))
    printed_at: Mapped[datetime | None] = mapped_column()


class HubStatus(TimestampMixin, Base):
    """The restaurant's hub (Hybrid venues): a small box in the restaurant running the same software
    in edge mode. Screens use it over the local network, so orders reach the kitchen when the
    internet is down; it syncs with the cloud whenever it can."""

    __tablename__ = "hub_status"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), primary_key=True)
    setup_code_hash: Mapped[str | None] = mapped_column(String(64))
    setup_expires_at: Mapped[datetime | None] = mapped_column()
    registered_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime | None] = mapped_column()  # last heartbeat through the internet
    lan_url: Mapped[str | None] = mapped_column(String(200))  # e.g. http://192.168.1.20:8000
    software: Mapped[str | None] = mapped_column(String(40))
    pending: Mapped[int] = mapped_column(default=0)  # changes the hub still has to send
    cloud_cursor: Mapped[str | None] = mapped_column(String(26))  # last cloud change the hub applied
    info: Mapped[dict[str, Any]] = mapped_column(default=dict)


class PosLink(TimestampMixin, Base):
    """The restaurant's own POS, connected (R-BRIDGE). Two ways, often both:
    push  we POST each order event to the POS's URL, signed with the shared secret
    pull  the POS calls /v1/pos/... with its key: read orders, mark them paid, send its menu (PLU)
    """

    __tablename__ = "pos_links"

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), primary_key=True)
    pos_name: Mapped[str] = mapped_column(String(80), default="")
    url: Mapped[str | None] = mapped_column(String(500))  # push: where order events go
    secret_enc: Mapped[str | None] = mapped_column(Text)  # push: HMAC secret (encrypted)
    events: Mapped[list[Any]] = mapped_column(default=list)
    key_digest: Mapped[str | None] = mapped_column(String(64), unique=True)  # pull: the POS's API key
    menu_from_pos: Mapped[bool] = mapped_column(default=False)  # prices and items come from the POS
    is_active: Mapped[bool] = mapped_column(default=True)
    last_ok_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(String(300))


class PosDelivery(IdMixin, TimestampMixin, Base):
    """One order event for the POS, retried until the POS answers 2xx."""

    __tablename__ = "pos_deliveries"
    __table_args__ = (Index("ix_pos_deliveries_status", "status", "next_try_at"),)

    venue_id: Mapped[str] = mapped_column(String(26), index=True)
    event: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[str | None] = mapped_column(String(26))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | sent | failed
    attempts: Mapped[int] = mapped_column(default=0)
    next_try_at: Mapped[datetime | None] = mapped_column()
    response_code: Mapped[int | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(String(300))


class PaymentAccount(IdMixin, TimestampMixin, Base):
    """The venue's merchant account with a payment provider (LankaQR today).

    The secret (API key) is stored encrypted and never leaves the server: screens only learn
    whether the method is ready.
    """

    __tablename__ = "payment_accounts"
    __table_args__ = (Index("ix_payment_accounts_venue_kind", "venue_id", "kind", unique=True),)

    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"))
    kind: Mapped[str] = mapped_column(String(20))  # lankaqr
    provider: Mapped[str] = mapped_column(String(40))
    merchant_id: Mapped[str] = mapped_column(String(80), default="")
    secret_enc: Mapped[str | None] = mapped_column(Text)
    secret_hint: Mapped[str | None] = mapped_column(String(8))  # last 4 characters, for the UI
    live: Mapped[bool] = mapped_column(default=False)  # False = the provider's test / sandbox mode
    status: Mapped[str] = mapped_column(String(20), default="not_tested")  # not_tested | ok | failed
    checked_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(String(300))
