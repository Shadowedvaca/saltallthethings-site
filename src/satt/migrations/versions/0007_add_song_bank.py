"""Add private Song Bank persistence

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "songs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("youtube_url", sa.Text(), nullable=False),
        sa.Column(
            "private_notes", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="'unused'"),
        sa.Column("assigned_idea_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('unused', 'used', 'retired')",
            name="songs_valid_status",
        ),
        sa.CheckConstraint(
            "(status = 'used' AND assigned_idea_id IS NOT NULL) OR "
            "(status <> 'used' AND assigned_idea_id IS NULL)",
            name="songs_assignment_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_idea_id"],
            ["satt.ideas.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assigned_idea_id", name="uq_songs_assigned_idea_id"),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_table("songs", schema="satt")
