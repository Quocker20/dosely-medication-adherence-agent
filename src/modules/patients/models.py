import uuid
from datetime import UTC, date, datetime, time, timezone
from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, Time, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class PatientProfile(Base):
    """Patient Profile database model."""

    __tablename__ = "patient_profiles"

    # Name matches migration 0003_access_idx exactly so autogenerate does not
    # propose a duplicate. Serves the ORDER BY created_at DESC of list_patients.
    __table_args__ = (
        Index("idx_patient_profiles_created_at", text("created_at DESC")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Asia/Ho_Chi_Minh"
    )
    privacy_consent_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    emergency_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
    # No onupdate= callable here: every write path is a Core update()/
    # on_conflict_do_update(), which never invokes it. Maintained instead by
    # the trg_*_set_updated_at DB trigger (migration 0005).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN required to load these.
    user: Mapped["User"] = relationship("User", lazy="raise")  # type: ignore # noqa: F821


class PatientRoutine(Base):
    """Patient daily routine timestamps database model."""

    __tablename__ = "patient_routines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    wake_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    breakfast_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    lunch_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    dinner_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    sleep_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
    # No onupdate= callable here: every write path is a Core update()/
    # on_conflict_do_update(), which never invokes it. Maintained instead by
    # the trg_*_set_updated_at DB trigger (migration 0005).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN required to load these.
    patient: Mapped["PatientProfile"] = relationship("PatientProfile", lazy="raise")


class RoutineOverride(Base):
    """Same-day override of one routine anchor (breakfast/lunch/dinner/sleep).

    Deliberately date-scoped rather than a second permanent routine: because
    expand_schedule (src/modules/agents/planner.py) computes each day of the
    horizon independently, an override matching only `override_date` is
    naturally inert on every other day the very next time the horizon is
    regenerated — no separate "revert" job is needed. `anchor` never includes
    "wake" — no dose slot anchors to it (see RoutineTimes docstring).
    """

    __tablename__ = "routine_overrides"

    __table_args__ = (
        UniqueConstraint("patient_id", "override_date", "anchor", name="uq_routine_overrides_patient_date_anchor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    override_date: Mapped[date] = mapped_column(Date, nullable=False)
    anchor: Mapped[str] = mapped_column(String(20), nullable=False)
    overridden_time: Mapped[time] = mapped_column(Time, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'ACTIVE' | 'REJECTED' | 'CANCELLED'. Added by migration 0029_routine_overrides.
    # get_active_overrides only feeds ACTIVE rows to the planner, so an
    # override whose run ended NEEDS_REVIEW cannot quietly take effect on a
    # later unrelated reschedule. CHECK constraint lives in the DB.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE", default="ACTIVE")
    # Set once the reschedule run it triggered reaches a terminal state — SET
    # NULL (not CASCADE) so a purged agent_runs row never deletes the audit
    # trail of what the patient actually reported.
    consumed_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )
    # No onupdate= callable here: every write path is a Core update()/
    # on_conflict_do_update(), which never invokes it. Maintained instead by
    # the trg_*_set_updated_at DB trigger (migration 0005).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )


## CaregiverLink moved to src.modules.caregivers.models -- a caregiver is no
## longer an actor reachable through a patients-owned table; it is its own
## slice (business record + Telegram send pipeline). See docs/
## caregiver-telegram-implementation-plan.md.
