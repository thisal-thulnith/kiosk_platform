"""printers, print queue and payment accounts (install-time setup)

Revision ID: a3b1d8f0c4e6
Revises: f2a0c7e9b3d5
Create Date: 2026-09-30 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "a3b1d8f0c4e6"
down_revision: Union[str, Sequence[str], None] = "f2a0c7e9b3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "printers",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("connection", sa.String(length=20), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("stations", sa.JSON(), nullable=False),
        sa.Column("device_id", sa.String(length=26), nullable=True),
        sa.Column("paper_mm", sa.Integer(), nullable=False),
        sa.Column("cash_drawer", sa.Boolean(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=True),
        sa.Column("token_enc", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", UTC(timezone=True), nullable=True),
        sa.Column("last_status", sa.JSON(), nullable=False),
        sa.Column("tested_at", UTC(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(op.f("ix_printers_venue_id"), "printers", ["venue_id"])
    op.create_table(
        "print_jobs",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("printer_id", sa.String(length=26), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("escpos", sa.LargeBinary(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("printed_at", UTC(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_print_jobs_venue_id"), "print_jobs", ["venue_id"])
    op.create_index("ix_print_jobs_printer_status", "print_jobs", ["printer_id", "status"])
    op.create_table(
        "payment_accounts",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("merchant_id", sa.String(length=80), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("secret_hint", sa.String(length=8), nullable=True),
        sa.Column("live", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("checked_at", UTC(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_accounts_venue_kind", "payment_accounts", ["venue_id", "kind"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payment_accounts_venue_kind", table_name="payment_accounts")
    op.drop_table("payment_accounts")
    op.drop_index("ix_print_jobs_printer_status", table_name="print_jobs")
    op.drop_index(op.f("ix_print_jobs_venue_id"), table_name="print_jobs")
    op.drop_table("print_jobs")
    op.drop_index(op.f("ix_printers_venue_id"), table_name="printers")
    op.drop_table("printers")
