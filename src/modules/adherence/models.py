import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class AdherenceLog(Base):
    """Append-only dose-intake action record database model."""

    __tablename__ = "adherence_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    # Nullable + ON DELETE CASCADE: an adherence log always belongs to a
    # patient, but not every log ties back to a still-existing scheduled
    # dose (e.g. the dose row is later purged) — patient_id is the durable
    # anchor for adherence reporting.
    scheduled_dose_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduled_doses.id", ondelete="CASCADE"),
        nullable=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
    action_source: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb"
    )
    # Header-supplied Idempotency-Key (POST /scheduled-doses/{id}/actions):
    # UNIQUE lets a retried/duplicate-delivered request be rejected at the DB
    # layer instead of double-recording the same dose action.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )


class HealthSurvey(Base):
    """Daily patient-submitted health survey database model."""

    __tablename__ = "health_surveys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    survey_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    answers_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN/selectinload required to load these.
    symptom_reports: Mapped[List["SymptomReport"]] = relationship(
        "SymptomReport", lazy="raise", order_by="SymptomReport.reported_at"
    )


class SymptomReport(Base):
    """Individual symptom entry tied to a health survey database model."""

    __tablename__ = "symptom_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    survey_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("health_surveys.id", ondelete="SET NULL"),
        nullable=True,
    )
    symptom_code: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)


class Alert(Base):
    """Safety alert / escalation record database model."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctor_profiles.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by_type: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="OPEN"
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mapped under a different Python attribute: "metadata" collides with
    # DeclarativeBase.metadata (the MetaData registry), so the ORM attribute
    # is renamed while the DB/JSON column name stays "metadata".
    alert_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="'{}'::jsonb"
    )
    # Header-supplied Idempotency-Key (POST /patients/{id}/sos): UNIQUE lets a
    # retried/duplicate-delivered SOS tap be rejected at the DB layer instead
    # of paging a doctor with duplicate CRITICAL alerts. Added by migration
    # 0010_slice7_alert_idem (column absent from the 0009 baseline).
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
    # No onupdate= callable: acknowledge/resolve are Core update() calls,
    # which never invoke it. Maintained by the trg_alerts_set_updated_at DB
    # trigger (migration 0009), same reason as scheduled_doses/patient_profiles.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
