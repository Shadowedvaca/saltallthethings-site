"""Add transcription_job to show_slots

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "show_slots",
        sa.Column("transcription_job", postgresql.JSONB(), nullable=True),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_column("show_slots", "transcription_job", schema="satt")
