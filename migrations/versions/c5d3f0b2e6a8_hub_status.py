"""hub status for hybrid venues (hub registration, heartbeat, change cursor)

Revision ID: c5d3f0b2e6a8
Revises: b4c2e9a1d5f7
Create Date: 2026-09-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "c5d3f0b2e6a8"
down_revision: Union[str, Sequence[str], None] = "b4c2e9a1d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "hub_status",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("setup_code_hash", sa.String(length=64), nullable=True),
        sa.Column("setup_expires_at", UTC(timezone=True), nullable=True),
        sa.Column("registered_at", UTC(timezone=True), nullable=True),
        sa.Column("last_seen_at", UTC(timezone=True), nullable=True),
        sa.Column("lan_url", sa.String(length=200), nullable=True),
        sa.Column("software", sa.String(length=40), nullable=True),
        sa.Column("pending", sa.Integer(), nullable=False),
        sa.Column("cloud_cursor", sa.String(length=26), nullable=True),
        sa.Column("info", sa.JSON(), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("venue_id"),
    )


def downgrade() -> None:
    op.drop_table("hub_status")
