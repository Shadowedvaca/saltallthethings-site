"""Enforce joke assignment integrity

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve existing assignments as authoritative and normalize legacy
    # "active" / orphaned "used" lifecycle values before adding constraints.
    op.execute(
        """
        UPDATE satt.jokes
        SET status = 'used'
        WHERE used_by_idea_id IS NOT NULL AND status <> 'used'
        """
    )
    op.execute(
        """
        UPDATE satt.jokes
        SET status = 'unused'
        WHERE used_by_idea_id IS NULL AND status IN ('active', 'used')
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT used_by_idea_id
                FROM satt.jokes
                WHERE used_by_idea_id IS NOT NULL
                GROUP BY used_by_idea_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce joke integrity: an idea has multiple assigned jokes';
            END IF;
        END
        $$;
        """
    )
    op.create_unique_constraint(
        "uq_jokes_used_by_idea_id",
        "jokes",
        ["used_by_idea_id"],
        schema="satt",
    )
    op.create_check_constraint(
        "jokes_valid_status",
        "jokes",
        "status IN ('unused', 'used', 'retired')",
        schema="satt",
    )
    op.create_check_constraint(
        "jokes_assignment_matches_status",
        "jokes",
        "(status = 'used' AND used_by_idea_id IS NOT NULL) OR "
        "(status <> 'used' AND used_by_idea_id IS NULL)",
        schema="satt",
    )
    op.alter_column(
        "jokes",
        "status",
        server_default=sa.text("'unused'"),
        existing_type=sa.Text(),
        existing_nullable=False,
        schema="satt",
    )


def downgrade() -> None:
    op.alter_column(
        "jokes",
        "status",
        server_default=sa.text("'active'"),
        existing_type=sa.Text(),
        existing_nullable=False,
        schema="satt",
    )
    op.drop_constraint(
        "jokes_assignment_matches_status",
        "jokes",
        type_="check",
        schema="satt",
    )
    op.drop_constraint(
        "jokes_valid_status",
        "jokes",
        type_="check",
        schema="satt",
    )
    op.drop_constraint(
        "uq_jokes_used_by_idea_id",
        "jokes",
        type_="unique",
        schema="satt",
    )
