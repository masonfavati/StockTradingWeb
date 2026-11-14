"""Store dated Alpaca universe snapshots for prospective coverage research.

Revision ID: c7a3b3dd42a1
Revises: 7724bc191cdd
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7a3b3dd42a1"
down_revision: str | Sequence[str] | None = "7724bc191cdd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universe_captures",
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("asset_count > 0", name="ck_universe_captures_count_positive"),
        sa.PrimaryKeyConstraint("captured_on"),
    )
    op.create_table(
        "universe_assets",
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("alpaca_asset_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("tradable", sa.Boolean(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_universe_assets_status"),
        sa.ForeignKeyConstraint(
            ["captured_on"], ["universe_captures.captured_on"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("captured_on", "alpaca_asset_id"),
    )
    op.create_index("ix_universe_assets_symbol", "universe_assets", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_universe_assets_symbol", table_name="universe_assets")
    op.drop_table("universe_assets")
    op.drop_table("universe_captures")
