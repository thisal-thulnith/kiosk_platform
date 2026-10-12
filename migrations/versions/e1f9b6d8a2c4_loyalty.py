"""loyalty members and member discounts on orders

Revision ID: e1f9b6d8a2c4
Revises: d0e8a5c7f1b3
Create Date: 2026-09-29 23:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "e1f9b6d8a2c4"
down_revision: Union[str, Sequence[str], None] = "d0e8a5c7f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("tenant_id", sa.String(length=26), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("consent_at", UTC(timezone=True), nullable=True),
        sa.Column("consent_text", sa.String(length=500), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("lifetime_points", sa.Integer(), nullable=False),
        sa.Column("visits", sa.Integer(), nullable=False),
        sa.Column("last_visit_at", UTC(timezone=True), nullable=True),
        sa.Column("forgotten_at", UTC(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "phone"),
    )
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_customers_tenant_id"), ["tenant_id"], unique=False)
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.String(length=26), nullable=True))
        batch_op.add_column(sa.Column("discount_bp", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("discount_label", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("discount_total", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("points_earned", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_index(batch_op.f("ix_orders_customer_id"), ["customer_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_orders_customer_id"))
        for col in ("points_earned", "discount_total", "discount_label", "discount_bp", "customer_id"):
            batch_op.drop_column(col)
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customers_tenant_id"))
    op.drop_table("customers")
