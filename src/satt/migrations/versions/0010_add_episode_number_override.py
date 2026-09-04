"""Add per-show episode-number override

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "show_slots",
        sa.Column("episode_number_override", sa.Integer(), nullable=True),
        schema="satt",
    )
    op.create_check_constraint(
        "show_slots_positive_episode_number_override",
        "show_slots",
        "episode_number_override IS NULL OR episode_number_override > 0",
        schema="satt",
    )


def downgrade() -> None:
    op.drop_constraint(
        "show_slots_positive_episode_number_override",
        "show_slots",
        type_="check",
        schema="satt",
    )
    op.drop_column("show_slots", "episode_number_override", schema="satt")
