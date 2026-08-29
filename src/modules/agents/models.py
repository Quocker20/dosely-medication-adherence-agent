import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ScheduledDose(Base):
    """Single medication intake event database model.

    original_scheduled_at is the plan's first-generated time; snooze
    (slice 7, RecordDoseActionRequest action=SNOOZE) only moves
    current_scheduled_at and bumps snooze_count — original_scheduled_at never
    changes, so adherence math can still tell how late a dose was taken.
    """

    __tablename__ = "scheduled_doses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    prescription_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prescription_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    original_scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Immutable prescription/slot snapshot selected by the planner. These
    # fields are nullable only for rows generated before migration 0011; never
    # infer a legacy row's slot-specific amount from the current item.
    dose_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    medication_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    dose_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    meal_relation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Rows with the same value are delivered in one notification. This is UX
    # metadata only and never changes either scheduled timestamp.
    notification_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    snooze_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Immutable snapshot of PrescriptionItem.is_critical at generation time,
    # same pattern as dose_slot/medication_id/dose_value above — cannot drift
    # from the item since items are DRAFT-locked once doses exist. Added by
    # migration 0021_dose_is_critical.
    is_critical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="FALSE"
    )
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )
    # No onupdate= callable: every write path is a Core update() (snooze,
    # dose actions), which never invokes it. Maintained by the
    # trg_scheduled_doses_set_updated_at DB trigger (migration 0008).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )


class AgentRun(Base):
    """LangGraph agent execution record database model."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    agent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prescriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    graph_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # error_code chỉ là tên class exception; message chi tiết (thuốc nào, cữ nào,
    # giãn cách thực tế bao nhiêu) nằm ở đây để portal hiện cho bác sĩ tự sửa.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_dose_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
    )
