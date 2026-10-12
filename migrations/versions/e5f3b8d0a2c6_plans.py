"""venue plans (packages / modules / screen limits) and the price book

Revision ID: e5f3b8d0a2c6
Revises: d4e2a7c9f1b3
Create Date: 2026-09-29 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f3b8d0a2c6"
down_revision: Union[str, Sequence[str], None] = "d4e2a7c9f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("venues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "price_book",
        sa.Column("item", sa.String(length=40), nullable=False),
        sa.Column("monthly", sa.Integer(), nullable=False),
        sa.Column("once", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("item"),
    )


def downgrade() -> None:
    op.drop_table("price_book")
    with op.batch_alter_table("venues", schema=None) as batch_op:
        batch_op.drop_column("plan")
