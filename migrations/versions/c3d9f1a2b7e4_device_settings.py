"""device settings (card terminal per screen)

Revision ID: c3d9f1a2b7e4
Revises: b7c1e2d4a9f0
Create Date: 2026-09-28 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d9f1a2b7e4"
down_revision: Union[str, Sequence[str], None] = "b7c1e2d4a9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("devices", schema=None) as batch_op:
        batch_op.drop_column("settings")
