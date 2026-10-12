"""service requests (call waiter, request bill, kiosk help)

Revision ID: d4e2a7c9f1b3
Revises: c3d9f1a2b7e4
Create Date: 2026-09-28 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "d4e2a7c9f1b3"
down_revision: Union[str, Sequence[str], None] = "c3d9f1a2b7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_requests",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("device_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("table_ref", sa.String(length=20), nullable=True),
        sa.Column("where", sa.String(length=120), nullable=False),
        sa.Column("order_id", sa.String(length=26), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=26), nullable=True),
        sa.Column("done_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("service_requests", schema=None) as batch_op:
        batch_op.create_index("ix_service_requests_open", ["venue_id", "status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("service_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_service_requests_open")
    op.drop_table("service_requests")
