"""kitchen flow: order priority and promised time, remake count, item prep minutes

Revision ID: a7b5d2f4c8e9
Revises: f6a4c9e1b3d7
Create Date: 2026-09-29 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "a7b5d2f4c8e9"
down_revision: Union[str, Sequence[str], None] = "f6a4c9e1b3d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("priority", sa.String(length=10), nullable=False, server_default="normal")
        )
        batch_op.add_column(
            sa.Column("promised_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("remake_count", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prep_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.drop_column("prep_minutes")
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_column("remake_count")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("promised_at")
        batch_op.drop_column("priority")
