import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class PatientProfile(Base):
    """Patient Profile database model."""

    __tablename__ = "patient_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctor_profiles.user_id", ondelete="SET NULL"),
        nullable=True,
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # lazy="raise" prevents implicit N+1 queries. Explicit JOIN required to load these.
    user: Mapped["User"] = relationship("User", lazy="raise")  # type: ignore # noqa: F821
    doctor: Mapped["DoctorProfile | None"] = relationship("DoctorProfile", lazy="raise")  # type: ignore # noqa: F821
