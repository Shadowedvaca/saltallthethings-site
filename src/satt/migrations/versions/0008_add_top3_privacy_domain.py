"""Add the private Top 3 planning domain

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "top3_concepts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rules", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("host_notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "ai_example",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column(
            "source", sa.Text(), nullable=False, server_default=sa.text("'manual'")
        ),
        sa.Column("ai_provider", sa.Text(), nullable=True),
        sa.Column("ai_model_id", sa.Text(), nullable=True),
        sa.Column("ai_generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
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
            "status IN ('active', 'retired')", name="top3_concepts_valid_status"
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'ai')", name="top3_concepts_valid_source"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(ai_example) = 'array' AND "
            "jsonb_array_length(ai_example) IN (0, 3)",
            name="top3_concepts_valid_ai_example",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["satt.users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )

    op.create_table(
        "top3_assignments",
        sa.Column("idea_id", sa.Text(), nullable=False),
        sa.Column("concept_id", sa.Text(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "assigned_at",
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
        sa.ForeignKeyConstraint(
            ["idea_id"], ["satt.ideas.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["satt.top3_concepts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["satt.users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("idea_id"),
        schema="satt",
    )

    op.create_table(
        "top3_submissions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("assignment_idea_id", sa.Text(), nullable=False),
        sa.Column("participant_type", sa.Text(), nullable=False),
        sa.Column("account_user_id", sa.Integer(), nullable=True),
        sa.Column("external_display_name", sa.Text(), nullable=True),
        sa.Column("external_type", sa.Text(), nullable=True),
        sa.Column("entered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("pick_1", sa.Text(), nullable=False),
        sa.Column("pick_2", sa.Text(), nullable=False),
        sa.Column("pick_3", sa.Text(), nullable=False),
        sa.Column(
            "private_discussion_notes",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
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
            "participant_type IN ('account', 'external')",
            name="top3_submissions_valid_participant_type",
        ),
        sa.CheckConstraint(
            "(participant_type = 'account' AND account_user_id IS NOT NULL "
            "AND external_display_name IS NULL AND external_type IS NULL "
            "AND entered_by_user_id IS NULL) OR "
            "(participant_type = 'external' AND account_user_id IS NULL "
            "AND external_display_name IS NOT NULL "
            "AND external_type IN ('guest', 'listener') "
            "AND entered_by_user_id IS NOT NULL)",
            name="top3_submissions_valid_owner",
        ),
        sa.CheckConstraint(
            "btrim(pick_1) <> '' AND btrim(pick_2) <> '' AND btrim(pick_3) <> ''",
            name="top3_submissions_nonempty_picks",
        ),
        sa.CheckConstraint(
            "lower(btrim(pick_1)) <> lower(btrim(pick_2)) AND "
            "lower(btrim(pick_1)) <> lower(btrim(pick_3)) AND "
            "lower(btrim(pick_2)) <> lower(btrim(pick_3))",
            name="top3_submissions_distinct_picks",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_idea_id"],
            ["satt.top3_assignments.idea_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_user_id"], ["satt.users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["entered_by_user_id"], ["satt.users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )
    op.create_index(
        "uq_top3_submissions_account_assignment",
        "top3_submissions",
        ["assignment_idea_id", "account_user_id"],
        unique=True,
        schema="satt",
        postgresql_where=sa.text("participant_type = 'account'"),
    )

    op.create_table(
        "top3_reveals",
        sa.Column("viewer_user_id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column(
            "revealed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["viewer_user_id"], ["satt.users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["satt.top3_submissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("viewer_user_id", "submission_id"),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_table("top3_reveals", schema="satt")
    op.drop_index(
        "uq_top3_submissions_account_assignment",
        table_name="top3_submissions",
        schema="satt",
    )
    op.drop_table("top3_submissions", schema="satt")
    op.drop_table("top3_assignments", schema="satt")
    op.drop_table("top3_concepts", schema="satt")
