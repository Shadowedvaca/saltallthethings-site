"""Add production_file_key and asset_inventory to show_slots

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "show_slots",
        sa.Column("production_file_key", sa.Text(), nullable=True),
        schema="satt",
    )
    op.add_column(
        "show_slots",
        sa.Column("asset_inventory", postgresql.JSONB(), nullable=True),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_column("show_slots", "asset_inventory", schema="satt")
    op.drop_column("show_slots", "production_file_key", schema="satt")
