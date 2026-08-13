import uuid
from datetime import date, datetime, time, timezone
from typing import List
from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, Time, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class CaregiverLink(Base):
    """Caregiver-to-Patient association link database model."""

    __tablename__ = "caregiver_links"

    # Backs both the duplicate-link guard (create) and the by-patient list scan
    # (leading column) with a single index. See migration 0004.
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "caregiver_user_id", name="uq_caregiver_links_patient_caregiver"
        ),
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
    caregiver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_label: Mapped[str | None] = mapped_column(
        "relationship", String(50), nullable=True
    )
    channels: Mapped[List[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
