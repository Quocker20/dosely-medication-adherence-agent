"""Notification dispatch service for consolidated dose reminders."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.repository import NotificationRepository
from src.modules.agents.repository import ScheduledDoseRepository

logger = logging.getLogger(__name__)


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
    def _merge_doses(doses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate medications by name, summing their dose_value.

        E.g. two entries of Metformin 500mg (1 viên each) become one entry
        Metformin 500mg (2 viên).
        """
        from collections import OrderedDict
        from decimal import Decimal

        merged: OrderedDict[str, Dict[str, Any]] = OrderedDict()
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
        scheduled_at: datetime, doses: List[Dict[str, Any]], timezone_str: str = "Asia/Ho_Chi_Minh"
    ) -> Tuple[str, str]:
        """Generate user-friendly title and consolidated message body.

        Merges duplicate medications by name and converts UTC to local timezone.
        """
        try:
            from zoneinfo import ZoneInfo
            if scheduled_at.tzinfo is None:
                local_dt = scheduled_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(timezone_str))
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
    ) -> List[NotificationDelivery]:
        """Scan all PENDING doses due at or before cutoff, group by (patient_id, current_scheduled_at),
        and persist consolidated notification deliveries with junction items."""
        grouped = await self._dose_repo.get_due_dose_groups(cutoff)
        new_deliveries: List[NotificationDelivery] = []
        final_deliveries: List[NotificationDelivery] = []

        # 1. Tạo các bản ghi delivery
        for (patient_id, scheduled_at), doses in grouped.items():
            dose_ids = [d["scheduled_dose_id"] for d in doses]
            title, body = self.format_notification_text(scheduled_at, doses)
            sorted_dose_ids_str = ",".join(sorted(str(d_id) for d_id in dose_ids))
            doses_hash = hashlib.sha256(sorted_dose_ids_str.encode("utf-8")).hexdigest()[:16]
            idempotency_key = (
                f"notif:dose_group:{patient_id}:{scheduled_at.isoformat()}:{doses_hash}"
            )

            existing = await self._notif_repo.get_delivery_by_idempotency_key(
                idempotency_key
            )
            if existing is not None:
                final_deliveries.append(existing)
                continue

            delivery = await self._notif_repo.create_grouped_delivery(
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
