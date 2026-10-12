"""upsell suggestions on menu items and the source of order lines

Revision ID: c9d7f4b6e0a2
Revises: b8c6e3a5d9f1
Create Date: 2026-09-29 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d7f4b6e0a2"
down_revision: Union[str, Sequence[str], None] = "b8c6e3a5d9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("suggest_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_column("source")
    with op.batch_alter_table("menu_items", schema=None) as batch_op:
        batch_op.drop_column("suggest_ids")
