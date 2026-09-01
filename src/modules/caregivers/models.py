import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class CaregiverLink(Base):
    """A registered contact who receives Telegram notifications about one
    patient. Not a `users` row and never authenticates -- caregiver-ness is
    entirely a fact of this table, addressed only through telegram_chat_id
    once bound. phone is retained for the doctor's own contact use;
    Telegram has no phone -> chat_id lookup, so it never addresses a send.
    """

    __tablename__ = "caregiver_links"

    __table_args__ = (
        UniqueConstraint("patient_id", "phone", name="uq_caregiver_links_patient_phone"),
        CheckConstraint(
            "status IN ('PENDING_BINDING','ACTIVE','BLOCKED','INACTIVE')",
            name="ck_caregiver_links_status",
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
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    relationship_label: Mapped[str | None] = mapped_column(
        "relationship", String(50), nullable=True
    )
    # One-time binding code shown to the patient as a t.me deep link
    # (?start=<code>), delivered to the bot as "/start <code>" the moment
    # the caregiver taps it. NULL once bound (cleared atomically by the
    # binding CAS in CaregiverRepository.bind_by_code).
    link_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # NULL == undeliverable: no Telegram send can ever address this link
    # until a webhook update binds it. BigInteger, not Integer -- Telegram
    # chat ids exceeded 32 bits in 2021.
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_bound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Diagnostics only -- unlike the Zalo predecessor, no claim query gates
    # on this (Telegram has no re-engagement window to expire). Refreshed
    # on every webhook update from a known chat_id; used only to show
    # "last seen" in the caregiver-list UI.
    telegram_last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Load-bearing: the T2 (CG_REPORT) cadence anchor, written atomically
    # by the same claim statement that selects a link for sending
    # (CaregiverRepository.claim_due_reports) -- exists so the nightly scan
    # is a plain indexed range predicate on this small table instead of a
    # correlated aggregate over notification_deliveries per link.
    last_report_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Display only (caregiver-list UI "last notified") -- no claim query
    # depends on this either.
    last_message_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING_BINDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN required to load these.
    patient: Mapped["PatientProfile"] = relationship(  # type: ignore # noqa: F821
        "PatientProfile", lazy="raise"
    )
