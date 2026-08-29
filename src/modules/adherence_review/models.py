import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AdherenceReview(Base):
    """Nightly graded-severity review record database model.

    One row per patient per night, written ONLY when severity is not NONE —
    an adherent patient generates no row. See migration
    0022_adherence_reviews and docs/graded-adherence-implementation.md for
    the full design (rules decide severity, LLM classifies remedy_class only
    and cannot revise severity).
    """

    __tablename__ = "adherence_reviews"

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
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)

    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    # Running counter carried forward from the prior night's row (reset to 1
    # on any severity change, or on a gap in review history) — NOT
    # recomputed by counting rows. See AdherenceReviewService.resolve_action.
    days_in_severity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    remedy_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(30), nullable=False)

    # The exact numbers that produced `severity`, frozen for audit — an
    # alert must be reconstructable even after later dose actions change the
    # underlying scheduled_doses rows.
    indicators: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb"
    )

    llm_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_deliveries.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )
