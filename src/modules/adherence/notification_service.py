"""Notification dispatch service for consolidated dose reminders."""
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.repository import NotificationRepository
from src.modules.agents.repository import ScheduledDoseRepository

logger = logging.getLogger(__name__)

# The only template that produces dose-linked deliveries. The send-time
# freshness guard keys off this rather than off the presence of linked doses:
# rescheduling hard-deletes doses and the junction rows cascade away with
# them, so "has no linked doses" cannot distinguish a stale reminder from an
# alert delivery, which must never be held back.
DOSE_REMINDER_TEMPLATE_CODE = "DOSE_REMINDER_GROUPED"


class NotificationDispatchService:
    """Service that scans due scheduled doses and consolidates concurrent
    medications for the same patient into a single grouped notification delivery."""

    def __init__(
        self,
        db: AsyncSession,
        scheduled_dose_repository: ScheduledDoseRepository,
        notification_repository: NotificationRepository,
    ) -> None:
        self._db = db
        self._dose_repo = scheduled_dose_repository
        self._notif_repo = notification_repository

    @staticmethod
    def _merge_doses(doses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge duplicate medications by name, summing their dose_value.

        E.g. two entries of Metformin 500mg (1 viên each) become one entry
        Metformin 500mg (2 viên).
        """
        from collections import OrderedDict
        from decimal import Decimal

        merged: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for d in doses:
            name = d.get("medication_name") or "thuốc"
            unit = d.get("dose_unit") or "viên"
            key = f"{name}|{unit}"
            if key in merged:
                existing_val = merged[key].get("dose_value") or Decimal(0)
                new_val = d.get("dose_value") or Decimal(0)
                merged[key]["dose_value"] = Decimal(str(existing_val)) + Decimal(str(new_val))
            else:
                merged[key] = {
                    "medication_name": name,
                    "dose_value": Decimal(str(d.get("dose_value") or 0)),
                    "dose_unit": unit,
                }
        return list(merged.values())

    @staticmethod
    def format_notification_text(
        scheduled_at: datetime, doses: list[dict[str, Any]], timezone_str: str = "Asia/Ho_Chi_Minh"
    ) -> tuple[str, str]:
        """Generate user-friendly title and consolidated message body.

        Merges duplicate medications by name and converts UTC to local timezone.
        """
        try:
            from zoneinfo import ZoneInfo
            if scheduled_at.tzinfo is None:
                local_dt = scheduled_at.replace(tzinfo=UTC).astimezone(ZoneInfo(timezone_str))
            else:
                local_dt = scheduled_at.astimezone(ZoneInfo(timezone_str))
        except Exception:
            local_dt = scheduled_at

        time_str = local_dt.strftime("%H:%M")

        # Merge duplicate medications
        merged = NotificationDispatchService._merge_doses(doses)

        def _format_amount(val, unit) -> str:
            if not val:
                return ""
            # Display as integer if whole number (e.g. 2 instead of 2.000)
            int_val = int(val)
            display = str(int_val) if val == int_val else str(val)
            return f" ({display} {unit})"

        title = f"Nhắc nhở uống thuốc ({time_str})"

        if len(merged) == 1:
            d = merged[0]
            name = d.get("medication_name") or "thuốc"
            amount_str = _format_amount(d.get("dose_value"), d.get("dose_unit") or "viên")
            body = f"Đến giờ uống {name}{amount_str}."
        else:
            items_desc = []
            for d in merged:
                name = d.get("medication_name") or "thuốc"
                amount_str = _format_amount(d.get("dose_value"), d.get("dose_unit") or "viên")
                items_desc.append(f"{name}{amount_str}")
            body = f"Đến giờ uống {len(merged)} loại thuốc: {', '.join(items_desc)}."
        return title, body

    async def create_consolidated_reminders(
        self, cutoff: datetime
    ) -> list[NotificationDelivery]:
        """Scan all PENDING doses due at or before cutoff, group by (patient_id, current_scheduled_at),
        and persist consolidated notification deliveries with junction items."""
        # Doses overdue by more than missed_dose_overdue_minutes belong to the
        # missed-dose scan (audit P-02); never look further back than that.
        not_before = cutoff - timedelta(minutes=get_settings().missed_dose_overdue_minutes)
        grouped = await self._dose_repo.get_due_dose_groups(cutoff, not_before=not_before)
        new_deliveries: list[NotificationDelivery] = []
        final_deliveries: list[NotificationDelivery] = []

        # 1. Build every group's idempotency key, then look them all up in one query.
        prepared: list[tuple[uuid.UUID, datetime, list[dict[str, Any]], list[uuid.UUID], str]] = []
        for (patient_id, scheduled_at), doses in grouped.items():
            dose_ids = [d["scheduled_dose_id"] for d in doses]
            sorted_dose_ids_str = ",".join(sorted(str(d_id) for d_id in dose_ids))
            doses_hash = hashlib.sha256(sorted_dose_ids_str.encode("utf-8")).hexdigest()[:16]
            idempotency_key = f"notif:dose_group:{patient_id}:{scheduled_at.isoformat()}:{doses_hash}"
            prepared.append((patient_id, scheduled_at, doses, dose_ids, idempotency_key))
        existing_by_key = await self._notif_repo.get_deliveries_by_idempotency_keys(
            [key for *_, key in prepared]
        )

        for patient_id, scheduled_at, doses, dose_ids, idempotency_key in prepared:
            existing = existing_by_key.get(idempotency_key)
            if existing is not None:
                final_deliveries.append(existing)
                continue

            title, body = self.format_notification_text(scheduled_at, doses)
            delivery, created = await self._notif_repo.create_grouped_delivery(
                recipient_user_id=patient_id,
                channel="APP_NOTIFICATION",
                template_code="DOSE_REMINDER_GROUPED",
                scheduled_at=scheduled_at,
                title=title,
                body=body,
                scheduled_dose_ids=dose_ids,
                metadata={"dose_ids": [str(d_id) for d_id in dose_ids]},
                idempotency_key=idempotency_key,
            )
            if created:
                new_deliveries.append(delivery)
            final_deliveries.append(delivery)

        if new_deliveries:
            await self._db.commit()

        # 2. Enqueue Celery task gửi push notification cho các delivery mới tạo
        if new_deliveries:
            try:
                from src.modules.agents.tasks import send_notification_task

                for delivery in new_deliveries:
                    send_notification_task.delay(str(delivery.id))
            except Exception as exc:
                logger.error("Failed to enqueue send_notification_task: %s", exc)

        return final_deliveries

    async def requeue_stale_deliveries(self, now: datetime) -> list[uuid.UUID]:
        """Re-enqueue deliveries whose Celery message was lost (audit O-01).

        There is no outbox: the task is enqueued after the delivery row commits,
        so a crash or broker blip in between leaves a QUEUED row nobody sends.
        A delivery whose worker died mid-send is stuck in SENDING and is treated
        the same way once it is older than the stale threshold. Re-enqueueing is
        safe because send_notification atomically claims the row first.
        """
        settings = get_settings()
        stale_ids = await self._notif_repo.list_stale_delivery_ids(
            now,
            queued_after=timedelta(minutes=settings.notification_requeue_after_minutes),
            stale_after=timedelta(minutes=settings.notification_sending_stale_minutes),
            lookback=timedelta(hours=settings.notification_requeue_lookback_hours),
        )
        if not stale_ids:
            return []

        # Stamp before enqueueing and commit, so overlapping/next scans skip
        # these rows while the messages sit in a backed-up queue.
        await self._notif_repo.mark_requeued(stale_ids, now)
        await self._db.commit()

        from src.modules.agents.tasks import send_notification_task

        enqueued: list[uuid.UUID] = []
        for delivery_id in stale_ids:
            try:
                send_notification_task.delay(str(delivery_id))
                enqueued.append(delivery_id)
            except Exception:
                logger.error("Failed to re-enqueue delivery %s", delivery_id, exc_info=True)
        logger.info("Re-enqueued %d stale notification deliveries", len(enqueued))
        return enqueued
