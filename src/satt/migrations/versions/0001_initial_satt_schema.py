"""Initial SATT schema

Revision ID: 0001
Revises:
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create satt schema
    op.execute("CREATE SCHEMA IF NOT EXISTS satt")

    # satt.users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        schema="satt",
    )

    # satt.invite_codes
    op.create_table(
        "invite_codes",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["satt.users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("code"),
        schema="satt",
    )

    # satt.config
    op.create_table(
        "config",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="single_row"),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )

    # satt.ideas
    op.create_table(
        "ideas",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("titles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("selected_title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("outline", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="'draft'"),
        sa.Column("image_file_id", sa.Text(), nullable=True),
        sa.Column("raw_notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )

    # satt.jokes
    op.create_table(
        "jokes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="'active'"),
        sa.Column("source", sa.Text(), nullable=False, server_default="'manual'"),
        sa.Column("used_by_idea_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["used_by_idea_id"],
            ["satt.ideas.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )

    # satt.show_slots
    op.create_table(
        "show_slots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("episode_number", sa.Text(), nullable=False),
        sa.Column("episode_num", sa.Integer(), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column(
            "is_rollout", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("release_date_override", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="satt",
    )

    # satt.assignments
    op.create_table(
        "assignments",
        sa.Column("slot_id", sa.Text(), nullable=False),
        sa.Column("idea_id", sa.Text(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            ["satt.ideas.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["satt.show_slots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("slot_id"),
        schema="satt",
    )


def downgrade() -> None:
    op.drop_table("assignments", schema="satt")
    op.drop_table("show_slots", schema="satt")
    op.drop_table("jokes", schema="satt")
    op.drop_table("ideas", schema="satt")
    op.drop_table("config", schema="satt")
    op.drop_table("invite_codes", schema="satt")
    op.drop_table("users", schema="satt")
    op.execute("DROP SCHEMA IF EXISTS satt")
