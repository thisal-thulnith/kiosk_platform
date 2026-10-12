"""combos (menu item slots) and combo parts on order items

Revision ID: f6a4c9e1b3d7
Revises: e5f3b8d0a2c6
Create Date: 2026-09-29 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a4c9e1b3d7"
down_revision: Union[str, Sequence[str], None] = "e5f3b8d0a2c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("combo_slots", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_position", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_column("parent_position")
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.drop_column("combo_slots")
