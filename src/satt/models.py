"""SQLAlchemy ORM models for the SATT platform.

satt schema: users, invite_codes, config, ideas, jokes, show_slots, assignments
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# satt.users
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "satt"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    invite_codes_created: Mapped[list["InviteCode"]] = relationship(
        back_populates="created_by", foreign_keys="InviteCode.created_by_user_id"
    )


# ---------------------------------------------------------------------------
# satt.invite_codes
# ---------------------------------------------------------------------------


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = {"schema": "satt"}

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("satt.users.id", ondelete="SET NULL")
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    created_by: Mapped[Optional[User]] = relationship(
        back_populates="invite_codes_created", foreign_keys=[created_by_user_id]
    )


# ---------------------------------------------------------------------------
# satt.config
# ---------------------------------------------------------------------------


class Config(Base):
    __tablename__ = "config"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        {"schema": "satt"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# satt.ideas
# ---------------------------------------------------------------------------


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = {"schema": "satt"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    titles: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    selected_title: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    outline: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'draft'")
    image_file_id: Mapped[Optional[str]] = mapped_column(Text)
    raw_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="idea")
    jokes_used: Mapped[list["Joke"]] = relationship(back_populates="used_by_idea")


# ---------------------------------------------------------------------------
# satt.jokes
# ---------------------------------------------------------------------------


class Joke(Base):
    __tablename__ = "jokes"
    __table_args__ = {"schema": "satt"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'active'")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="'manual'")
    used_by_idea_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("satt.ideas.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    used_by_idea: Mapped[Optional[Idea]] = relationship(back_populates="jokes_used")


# ---------------------------------------------------------------------------
# satt.show_slots
# ---------------------------------------------------------------------------


class ShowSlot(Base):
    __tablename__ = "show_slots"
    __table_args__ = {"schema": "satt"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    episode_number: Mapped[str] = mapped_column(Text, nullable=False)
    episode_num: Mapped[int] = mapped_column(Integer, nullable=False)
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_rollout: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    release_date_override: Mapped[Optional[date]] = mapped_column(Date)
    production_file_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_inventory: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="slot")


# ---------------------------------------------------------------------------
# satt.assignments
# ---------------------------------------------------------------------------


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = {"schema": "satt"}

    slot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("satt.show_slots.id", ondelete="CASCADE"), primary_key=True
    )
    idea_id: Mapped[str] = mapped_column(
        Text, ForeignKey("satt.ideas.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    slot: Mapped[ShowSlot] = relationship(back_populates="assignment")
    idea: Mapped[Idea] = relationship(back_populates="assignment")
