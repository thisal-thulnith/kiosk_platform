"""inventory (stock items, stock moves) and AI price offers

Revision ID: f2a0c7e9b3d5
Revises: e1f9b6d8a2c4
Create Date: 2026-09-30 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import kiosk.infra.models.base


# revision identifiers, used by Alembic.
revision: str = "f2a0c7e9b3d5"
down_revision: Union[str, Sequence[str], None] = "e1f9b6d8a2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = kiosk.infra.models.base.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "stock_items",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("menu_item_id", sa.String(length=26), nullable=False),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("low_at", sa.Integer(), nullable=False),
        sa.Column("auto_86", sa.Boolean(), nullable=False),
        sa.Column("auto_off", sa.Boolean(), nullable=False),
        sa.Column("perishable_until", UTC(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "menu_item_id"),
    )
    op.create_index(op.f("ix_stock_items_venue_id"), "stock_items", ["venue_id"])
    op.create_table(
        "stock_moves",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("menu_item_id", sa.String(length=26), nullable=False),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("order_id", sa.String(length=26), nullable=True),
        sa.Column("by", sa.String(length=200), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_moves_venue_time", "stock_moves", ["venue_id", "created_at"])
    op.create_table(
        "price_offers",
        sa.Column("venue_id", sa.String(length=26), nullable=False),
        sa.Column("menu_item_id", sa.String(length=26), nullable=False),
        sa.Column("discount_bp", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("starts_at", UTC(timezone=True), nullable=True),
        sa.Column("ends_at", UTC(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=200), nullable=True),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", UTC(timezone=True), nullable=False),
        sa.Column("updated_at", UTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_price_offers_venue_id"), "price_offers", ["venue_id"])
    op.create_index(op.f("ix_price_offers_menu_item_id"), "price_offers", ["menu_item_id"])


def downgrade() -> None:
    op.drop_table("price_offers")
    op.drop_index("ix_stock_moves_venue_time", table_name="stock_moves")
    op.drop_table("stock_moves")
    op.drop_index(op.f("ix_stock_items_venue_id"), table_name="stock_items")
    op.drop_table("stock_items")
