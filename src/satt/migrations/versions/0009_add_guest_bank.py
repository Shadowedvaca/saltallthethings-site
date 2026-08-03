"""Add reusable private Guest Bank persistence

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "private_notes", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
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
            "status IN ('active', 'archived')", name="guests_valid_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )
    op.create_table(
        "guest_assignments",
        sa.Column("guest_id", sa.Text(), nullable=False),
        sa.Column("idea_id", sa.Text(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["guest_id"], ["satt.guests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["satt.ideas.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("guest_id", "idea_id"),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_table("guest_assignments", schema="satt")
    op.drop_table("guests", schema="satt")
