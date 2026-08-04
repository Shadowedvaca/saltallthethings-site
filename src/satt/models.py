"""SQLAlchemy ORM models for the SATT platform.

satt schema: users, invite_codes, config, ideas, jokes, songs, guests,
guest_assignments, show_slots, assignments
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
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
# satt.data_revision
# ---------------------------------------------------------------------------


class DataRevision(Base):
    __tablename__ = "data_revision"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        {"schema": "satt"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
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
    ai_provider: Mapped[Optional[str]] = mapped_column(Text)
    ai_model_id: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="idea")
    jokes_used: Mapped[list["Joke"]] = relationship(back_populates="used_by_idea")
    assigned_song: Mapped[Optional["Song"]] = relationship(
        back_populates="assigned_idea", uselist=False
    )
    top3_assignment: Mapped[Optional["Top3Assignment"]] = relationship(
        back_populates="idea", uselist=False
    )
    guest_assignments: Mapped[list["GuestAssignment"]] = relationship(
        back_populates="idea"
    )


# ---------------------------------------------------------------------------
# satt.jokes
# ---------------------------------------------------------------------------


class Joke(Base):
    __tablename__ = "jokes"
    __table_args__ = (
        UniqueConstraint("used_by_idea_id", name="uq_jokes_used_by_idea_id"),
        CheckConstraint(
            "status IN ('unused', 'used', 'retired')",
            name="jokes_valid_status",
        ),
        CheckConstraint(
            "(status = 'used' AND used_by_idea_id IS NOT NULL) OR "
            "(status <> 'used' AND used_by_idea_id IS NULL)",
            name="jokes_assignment_matches_status",
        ),
        {"schema": "satt"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'unused'")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="'manual'")
    used_by_idea_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("satt.ideas.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    used_by_idea: Mapped[Optional[Idea]] = relationship(back_populates="jokes_used")


# ---------------------------------------------------------------------------
# satt.songs
# ---------------------------------------------------------------------------


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (
        UniqueConstraint("assigned_idea_id", name="uq_songs_assigned_idea_id"),
        CheckConstraint(
            "status IN ('unused', 'used', 'retired')",
            name="songs_valid_status",
        ),
        CheckConstraint(
            "(status = 'used' AND assigned_idea_id IS NOT NULL) OR "
            "(status <> 'used' AND assigned_idea_id IS NULL)",
            name="songs_assignment_matches_status",
        ),
        {"schema": "satt"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    artist: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    youtube_url: Mapped[str] = mapped_column(Text, nullable=False)
    private_notes: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="''"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'unused'")
    assigned_idea_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("satt.ideas.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assigned_idea: Mapped[Optional[Idea]] = relationship(back_populates="assigned_song")


# ---------------------------------------------------------------------------
# Private reusable Guest Bank
# ---------------------------------------------------------------------------


class Guest(Base):
    __tablename__ = "guests"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="guests_valid_status"),
        {"schema": "satt"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    private_notes: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="''"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'active'")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assignments: Mapped[list["GuestAssignment"]] = relationship(back_populates="guest")


class GuestAssignment(Base):
    __tablename__ = "guest_assignments"
    __table_args__ = ({"schema": "satt"},)

    guest_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("satt.guests.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    idea_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("satt.ideas.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    guest: Mapped[Guest] = relationship(back_populates="assignments")
    idea: Mapped[Idea] = relationship(back_populates="guest_assignments")


# ---------------------------------------------------------------------------
# Private Top 3 planning
# ---------------------------------------------------------------------------


class Top3Concept(Base):
    __tablename__ = "top3_concepts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retired')", name="top3_concepts_valid_status"
        ),
        CheckConstraint(
            "source IN ('manual', 'ai')", name="top3_concepts_valid_source"
        ),
        CheckConstraint(
            "jsonb_typeof(ai_example) = 'array' AND "
            "jsonb_array_length(ai_example) IN (0, 3)",
            name="top3_concepts_valid_ai_example",
        ),
        {"schema": "satt"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[str] = mapped_column(Text, nullable=False, server_default="''")
    host_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="''")
    ai_example: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'active'")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="'manual'")
    ai_provider: Mapped[Optional[str]] = mapped_column(Text)
    ai_model_id: Mapped[Optional[str]] = mapped_column(Text)
    ai_generated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satt.users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assignments: Mapped[list["Top3Assignment"]] = relationship(back_populates="concept")


class Top3Assignment(Base):
    __tablename__ = "top3_assignments"
    __table_args__ = ({"schema": "satt"},)

    idea_id: Mapped[str] = mapped_column(
        Text, ForeignKey("satt.ideas.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[str] = mapped_column(
        Text, ForeignKey("satt.top3_concepts.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satt.users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    idea: Mapped[Idea] = relationship(back_populates="top3_assignment")
    concept: Mapped[Top3Concept] = relationship(back_populates="assignments")
    submissions: Mapped[list["Top3Submission"]] = relationship(
        back_populates="assignment"
    )


class Top3Submission(Base):
    __tablename__ = "top3_submissions"
    __table_args__ = (
        CheckConstraint(
            "participant_type IN ('account', 'external')",
            name="top3_submissions_valid_participant_type",
        ),
        CheckConstraint(
            "(participant_type = 'account' AND account_user_id IS NOT NULL "
            "AND external_display_name IS NULL AND external_type IS NULL "
            "AND entered_by_user_id IS NULL) OR "
            "(participant_type = 'external' AND account_user_id IS NULL "
            "AND external_display_name IS NOT NULL "
            "AND external_type IN ('guest', 'listener') "
            "AND entered_by_user_id IS NOT NULL)",
            name="top3_submissions_valid_owner",
        ),
        CheckConstraint(
            "btrim(pick_1) <> '' AND btrim(pick_2) <> '' AND btrim(pick_3) <> ''",
            name="top3_submissions_nonempty_picks",
        ),
        CheckConstraint(
            "lower(btrim(pick_1)) <> lower(btrim(pick_2)) AND "
            "lower(btrim(pick_1)) <> lower(btrim(pick_3)) AND "
            "lower(btrim(pick_2)) <> lower(btrim(pick_3))",
            name="top3_submissions_distinct_picks",
        ),
        Index(
            "uq_top3_submissions_account_assignment",
            "assignment_idea_id",
            "account_user_id",
            unique=True,
            postgresql_where=text("participant_type = 'account'"),
        ),
        {"schema": "satt"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    assignment_idea_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("satt.top3_assignments.idea_id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_type: Mapped[str] = mapped_column(Text, nullable=False)
    account_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("satt.users.id", ondelete="RESTRICT")
    )
    external_display_name: Mapped[Optional[str]] = mapped_column(Text)
    external_type: Mapped[Optional[str]] = mapped_column(Text)
    entered_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("satt.users.id", ondelete="RESTRICT")
    )
    pick_1: Mapped[str] = mapped_column(Text, nullable=False)
    pick_2: Mapped[str] = mapped_column(Text, nullable=False)
    pick_3: Mapped[str] = mapped_column(Text, nullable=False)
    private_discussion_notes: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="''"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    assignment: Mapped[Top3Assignment] = relationship(back_populates="submissions")
    reveals: Mapped[list["Top3Reveal"]] = relationship(back_populates="submission")


class Top3Reveal(Base):
    __tablename__ = "top3_reveals"
    __table_args__ = ({"schema": "satt"},)

    viewer_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("satt.users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    submission_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("satt.top3_submissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revealed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    submission: Mapped[Top3Submission] = relationship(back_populates="reveals")


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
    is_rollout: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    release_date_override: Mapped[Optional[date]] = mapped_column(Date)
    production_file_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_inventory: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    transcription_job: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="slot")


# ---------------------------------------------------------------------------
# satt.assignments
# ---------------------------------------------------------------------------


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("idea_id", name="uq_assignments_idea_id"),
        {"schema": "satt"},
    )

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
