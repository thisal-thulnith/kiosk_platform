"""connection to the restaurant's own POS (push events, pull API, PLU codes)

Revision ID: e7f5b2d4a8c0
Revises: d6e4a1c3f7b9
Create Date: 2026-09-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "e7f5b2d4a8c0"
down_revision: Union[str, Sequence[str], None] = "d6e4a1c3f7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "pos_links",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("pos_name", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=True),
        sa.Column("menu_from_pos", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_ok_at", UTC(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("venue_id"),
        sa.UniqueConstraint("key_digest"),
    )
    op.create_table(
        "pos_deliveries",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("order_id", sa.String(length=26), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_try_at", UTC(timezone=True), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pos_deliveries_venue_id"), "pos_deliveries", ["venue_id"])
    op.create_index("ix_pos_deliveries_status", "pos_deliveries", ["status", "next_try_at"])
    with op.batch_alter_table("menu_items") as batch:
        batch.add_column(sa.Column("external_code", sa.String(length=40), nullable=True))
        batch.create_index("ix_menu_items_external_code", ["external_code"])


def downgrade() -> None:
    with op.batch_alter_table("menu_items") as batch:
        batch.drop_index("ix_menu_items_external_code")
        batch.drop_column("external_code")
    op.drop_index("ix_pos_deliveries_status", table_name="pos_deliveries")
    op.drop_index(op.f("ix_pos_deliveries_venue_id"), table_name="pos_deliveries")
    op.drop_table("pos_deliveries")
    op.drop_table("pos_links")
