"""Add AI provenance to ideas

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ideas",
        sa.Column("ai_provider", sa.Text(), nullable=True),
        schema="satt",
    )
    op.add_column(
        "ideas",
        sa.Column("ai_model_id", sa.Text(), nullable=True),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_column("ideas", "ai_model_id", schema="satt")
    op.drop_column("ideas", "ai_provider", schema="satt")
