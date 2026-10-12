"""guest texts: order ready and receipt links

Revision ID: d6e4a1c3f7b9
Revises: c5d3f0b2e6a8
Create Date: 2026-09-29 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "d6e4a1c3f7b9"
down_revision: Union[str, Sequence[str], None] = "c5d3f0b2e6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "sms_messages",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("order_id", sa.String(length=26), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_ref", sa.String(length=80), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("sent_at", UTC(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sms_messages_venue_id"), "sms_messages", ["venue_id"])
    op.create_index("ix_sms_status", "sms_messages", ["status", "created_at"])
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("notify_phone", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("notify_phone")
    op.drop_index("ix_sms_status", table_name="sms_messages")
    op.drop_index(op.f("ix_sms_messages_venue_id"), table_name="sms_messages")
    op.drop_table("sms_messages")
