"""payments remember the screen that took them (receipts print on that screen's printer)

Revision ID: b4c2e9a1d5f7
Revises: a3b1d8f0c4e6
Create Date: 2026-09-30 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c2e9a1d5f7"
down_revision: Union[str, Sequence[str], None] = "a3b1d8f0c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("device_id", sa.String(length=26), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("device_id")
