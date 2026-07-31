"""Add data revision and schedule integrity

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_revision",
        sa.Column("id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.CheckConstraint("id = 1", name="single_row"),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )
    op.execute("INSERT INTO satt.data_revision (id, revision) VALUES (1, 0)")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT idea_id
                FROM satt.assignments
                GROUP BY idea_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce schedule integrity: an idea is assigned to multiple slots';
            END IF;
        END
        $$;
        """
    )
    op.create_unique_constraint(
        "uq_assignments_idea_id",
        "assignments",
        ["idea_id"],
        schema="satt",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_assignments_idea_id",
        "assignments",
        type_="unique",
        schema="satt",
    )
    op.drop_table("data_revision", schema="satt")
