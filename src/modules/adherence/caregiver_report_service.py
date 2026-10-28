"""Periodic caregiver adherence report (CG_REPORT) generation."""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.adherence.repository import NotificationRepository
from src.modules.agents.repository import ScheduledDoseRepository
from src.modules.caregivers.repository import CaregiverRepository
from src.modules.patients.repository import PatientRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdherenceStats:
    total: int
    taken: int
    missed: int
    rate: float


def compute_adherence_stats(statuses: Iterable[str]) -> AdherenceStats:
    values = list(statuses)
    total = len(values)
    taken = sum(1 for s in values if s == "TAKEN")
    missed = sum(1 for s in values if s in ("MISSED", "SKIPPED"))
    rate = (taken / total * 100.0) if total > 0 else 100.0
    return AdherenceStats(total=total, taken=taken, missed=missed, rate=rate)


def build_report_body(interval_days: int, patient_name: str, stats: AdherenceStats) -> str:
    return (
        f"Báo cáo tuân thủ dùng thuốc định kỳ ({interval_days} ngày qua)\n"
        f"Người bệnh: {patient_name}\n"
        f"• Tổng số liều: {stats.total}\n"
        f"• Đã uống: {stats.taken}\n"
        f"• Quên/Bỏ lỡ: {stats.missed}\n"
        f"• Tỷ lệ tuân thủ: {stats.rate:.1f}%\n\n"
        f"Cảm ơn bạn đã đồng hành chăm sóc sức khỏe cùng Dosely."
    )


class CaregiverReportService:
    """Claims caregiver links due for a report and records one CG_REPORT
    delivery per link. Owns its transactions: the claim commits before any
    delivery is written, and each delivery commits on its own, so the caller
    must pass a session with no transaction open."""

    def __init__(
        self,
        db: AsyncSession,
        caregiver_repository: CaregiverRepository,
        notification_repository: NotificationRepository,
        scheduled_dose_repository: ScheduledDoseRepository,
        patient_repository: PatientRepository,
    ) -> None:
        self._db = db
        self._caregivers = caregiver_repository
        self._notifications = notification_repository
        self._doses = scheduled_dose_repository
        self._patients = patient_repository

    async def create_due_reports(self, now: datetime, interval_days: int) -> list[uuid.UUID]:
        """Returns the created delivery ids, which the caller enqueues for sending."""
        async with self._db.begin():
            claimed_links = await self._caregivers.claim_due_reports(now, interval_days)

        if not claimed_links:
            logger.info("No caregiver links due for adherence report at %s", now.isoformat())
            return []

        delivery_ids: list[uuid.UUID] = []
        start_date = now - timedelta(days=interval_days)
        for link in claimed_links:
            names = await self._patients.get_names_by_ids([link.patient_id])
            patient_name = names.get(link.patient_id) or "Người bệnh"
            statuses = await self._doses.get_statuses_in_window(link.patient_id, start_date, now)
            stats = compute_adherence_stats(statuses)
            body = build_report_body(interval_days, patient_name, stats)

            if self._db.in_transaction():
                await self._db.commit()

            async with self._db.begin():
                delivery = await self._notifications.create_caregiver_delivery(
                    caregiver_link_id=link.id,
                    template_code="CG_REPORT",
                    title=f"Báo cáo tuân thủ {patient_name}",
                    body=body,
                    metadata={
                        "patient_id": str(link.patient_id),
                        "interval_days": interval_days,
                        "total_doses": stats.total,
                        "taken_doses": stats.taken,
                        "missed_doses": stats.missed,
                        "adherence_rate": stats.rate,
                    },
                )
                delivery_ids.append(delivery.id)
        return delivery_ids
