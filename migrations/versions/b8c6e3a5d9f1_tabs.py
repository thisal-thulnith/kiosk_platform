"""dine-in tabs and waiter serve

Revision ID: b8c6e3a5d9f1
Revises: a7b5d2f4c8e9
Create Date: 2026-09-29 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "b8c6e3a5d9f1"
down_revision: Union[str, Sequence[str], None] = "a7b5d2f4c8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_tab", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(
            sa.Column("served_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("served_at")
        batch_op.drop_column("is_tab")
