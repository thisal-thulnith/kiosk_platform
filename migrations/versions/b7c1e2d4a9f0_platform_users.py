"""platform users (platform operator logins)

Revision ID: b7c1e2d4a9f0
Revises: 870438e43b9f
Create Date: 2026-09-28 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "b7c1e2d4a9f0"
down_revision: Union[str, Sequence[str], None] = "870438e43b9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_users",
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", kiosk.infra.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("platform_users")
