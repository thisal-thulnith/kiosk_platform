"""tables opened and closed by staff (table_access = staff_opens)

Revision ID: f8a6c3e5b9d1
Revises: e7f5b2d4a8c0
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "f8a6c3e5b9d1"
down_revision: Union[str, Sequence[str], None] = "e7f5b2d4a8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "table_states",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("table_ref", sa.String(length=20), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("opened_at", UTC(timezone=True), nullable=True),
        sa.Column("opened_by", sa.String(length=26), nullable=True),
        sa.Column("closed_at", UTC(timezone=True), nullable=True),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("venue_id", "table_ref"),
    )


def downgrade() -> None:
    op.drop_table("table_states")
