import uuid
from datetime import datetime, timezone
from typing import Any, List
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class DoctorProfile(Base):
    """Doctor Profile database model."""

    __tablename__ = "doctor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    license_no: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    specialty: Mapped[str | None] = mapped_column(String(150), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    user: Mapped["User"] = relationship("User", lazy="raise")  # type: ignore # noqa: F821


class AuditLog(Base):
    """Audit Log database model."""

    __tablename__ = "audit_logs"

    __table_args__ = (
        Index(
            "idx_audit_logs_entity_type_created",
            "entity_type",
            text("created_at DESC"),
        ),
        # Named to match what database_v1_init.sql already created. Declaring
        # it via `index=True` on the column instead would have SQLAlchemy
        # generate the name `ix_audit_logs_actor_user_id`, which autogenerate
        # then sees as missing and proposes adding — a second index over the
        # same column.
        Index("idx_audit_logs_actor_user_id", "actor_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    changed_fields: Mapped[List[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="NOW()",
    )

    # Relationship lazy="raise" prevents implicit N+1 queries. Explicit JOIN required if actor details needed.
    actor: Mapped["User | None"] = relationship("User", lazy="raise")  # type: ignore # noqa: F821
