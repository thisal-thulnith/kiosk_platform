"""AI decision log

Revision ID: d0e8a5c7f1b3
Revises: c9d7f4b6e0a2
Create Date: 2026-09-29 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "d0e8a5c7f1b3"
down_revision: Union[str, Sequence[str], None] = "c9d7f4b6e0a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_actions",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_actions", schema=None) as batch_op:
        batch_op.create_index("ix_ai_actions_venue_time", ["venue_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_actions", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_actions_venue_time")
    op.drop_table("ai_actions")
