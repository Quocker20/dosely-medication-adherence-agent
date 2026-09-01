import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Medication(Base):
    """Medication reference catalog database model."""

    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    composition: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uses: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )


class Prescription(Base):
    """Prescription database model."""

    __tablename__ = "prescriptions"

    # Name matches migration 0003_access_idx exactly so autogenerate does not
    # propose a duplicate. Backs the doctor-access EXISTS probe as an index-only
    # scan; see PatientRepository._has_prescribed_filter.
    __table_args__ = (Index("idx_prescriptions_doctor_patient", "doctor_id", "patient_id"),)

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
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctor_profiles.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    diagnosis_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN/selectinload required to load these.
    items: Mapped[list["PrescriptionItem"]] = relationship(
        "PrescriptionItem", lazy="raise", order_by="PrescriptionItem.created_at"
    )


class PrescriptionItem(Base):
    """Prescription line item (single medication dosing rule) database model."""

    __tablename__ = "prescription_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prescriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No FK to medications: display_name is a frozen snapshot taken at
    # write time, so this column must survive the referenced medication
    # being edited or deleted.
    medication_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dose_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    morning_dose: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    noon_dose: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    evening_dose: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bedtime_dose: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    route: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ORAL")
    meal_relation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    minimum_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Doctor-set on high-risk medications; snapshotted onto
    # ScheduledDose.is_critical at generation time (see planner.py). Added by
    # migration 0021_dose_is_critical.
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="FALSE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )
