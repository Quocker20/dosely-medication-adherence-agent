import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.chatbot.tools.safety_tools import count_missed_dose_streak
from src.core.config import get_settings
from src.modules.adherence.repository import AlertRepository
from src.modules.agents.repository import (
    ScheduledDoseRepository,
)

logger = logging.getLogger(__name__)


_MISSED_DOSE_TRIGGERED_BY_TYPE = "MISSED_DOSES"
_MISSED_DOSE_ALERT_TYPE = "RED_ALERT"
_MISSED_DOSE_ALERT_SEVERITY = "HIGH"


class MissedDoseScanService:
    """Celery-Beat-driven periodic scan (see tasks.py:scan_missed_doses_task).
    Trigger 1 of the Red Alert safety mechanism (cong_viec.md §4.1) — pure
    code, no LLM. Runs outside any authenticated HTTP request (there is no
    single patient's bearer token for a scan touching every patient), so it
    writes through AlertRepository directly rather than POST /patients/{id}/sos
    (the path chat-detected alerts use, which runs under the caller's own
    token — see safety_tools.py's _send_alert).

    The MISSED-flip half below covers every dose regardless of
    PrescriptionItem.is_critical — that's the state machine keeping
    scheduled_doses accurate, and narrowing it would leave non-critical
    overdue doses PENDING forever, retroactively actionable via
    apply_dose_action_cas. Only the streak-alert half is narrowed to
    critical doses (docs/graded-adherence-implementation.md Stage 2): a
    missed vitamin no longer pages a doctor identically to a missed
    anticoagulant. The general (any-medication) missed-dose-streak alert
    that used to run here is retired — the nightly graded-adherence review
    (Stage 3+) covers non-critical adherence trends instead."""

    def __init__(
        self,
        db: AsyncSession,
        scheduled_dose_repository: ScheduledDoseRepository,
        alert_repository: AlertRepository,
    ) -> None:
        self._db = db
        self._dose_repo = scheduled_dose_repository
        self._alert_repo = alert_repository

    async def run_scan(self) -> None:
        settings = get_settings()
        threshold = settings.missed_dose_alert_threshold
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=settings.missed_dose_overdue_minutes)

        async with self._db.begin():
            affected = await self._dose_repo.mark_overdue_pending_as_missed(cutoff)
        if not affected:
            return

        # Keep each patient's most-recently-missed CRITICAL dose id (for the
        # alert's triggered_by_id / idempotency key) — a single scan can flip
        # several overdue doses per patient at once, and a non-critical flip
        # must never become the tracked "last missed dose" for a critical
        # streak alert.
        last_dose_by_patient: dict[uuid.UUID, tuple[uuid.UUID, datetime]] = {}
        for patient_id, dose_id, scheduled_at, is_critical in affected:
            if not is_critical:
                continue
            prev = last_dose_by_patient.get(patient_id)
            if prev is None or scheduled_at > prev[1]:
                last_dose_by_patient[patient_id] = (dose_id, scheduled_at)

        patient_ids = list(last_dose_by_patient)
        if not patient_ids:
            # No critical dose was newly missed this tick for anyone — no
            # patient's critical streak could have changed since the last
            # scan, so there is nothing to recheck.
            return
        async with self._db.begin():
            streaks = await self._dose_repo.get_recent_critical_dose_statuses(
                patient_ids, lookback=threshold, before=now
            )

        for patient_id in patient_ids:
            doses = streaks.get(patient_id, [])
            if len(doses) < threshold or count_missed_dose_streak(doses) < threshold:
                continue
            last_dose_id, last_scheduled_at = last_dose_by_patient[patient_id]
            idempotency_key = f"missed-dose-streak:{patient_id}:{last_dose_id}"
            # A once-daily critical drug means "3+ consecutive" spans several
            # days, not one afternoon — name the span so the message doesn't
            # imply same-day urgency it may not have.
            span_days = max(1, (now.date() - last_scheduled_at.date()).days + 1)
            msg = (
                f"{threshold}+ liều thuốc quan trọng liên tiếp bị bỏ lỡ/quá giờ "
                f"(trong {span_days} ngày gần đây)."
            )
            created_deliveries: list[uuid.UUID] = []
            try:
                async with self._db.begin():
                    alert = await self._alert_repo.create_alert(
                        patient_id=patient_id,
                        triggered_by_type=_MISSED_DOSE_TRIGGERED_BY_TYPE,
                        triggered_by_id=last_dose_id,
                        alert_type=_MISSED_DOSE_ALERT_TYPE,
                        severity=_MISSED_DOSE_ALERT_SEVERITY,
                        message=msg,
                        idempotency_key=idempotency_key,
                    )
                    from sqlalchemy import select

                    from src.modules.adherence.repository import NotificationRepository
                    from src.modules.caregivers.repository import CaregiverRepository
                    from src.modules.patients.models import PatientProfile

                    cg_repo = CaregiverRepository(self._db)
                    links = await cg_repo.list_deliverable_for_patient(patient_id)
                    if links:
                        p_stmt = select(PatientProfile.name).where(PatientProfile.user_id == patient_id)
                        patient_name = (await self._db.execute(p_stmt)).scalar_one_or_none() or "Người bệnh"
                        cg_body = f"Cảnh báo bỏ lỡ thuốc - {patient_name}:\n{msg}"
                        notif_repo = NotificationRepository(self._db)
                        for link in links:
                            deliv = await notif_repo.create_caregiver_delivery(
                                caregiver_link_id=link.id,
                                template_code="CG_MISSED_DOSE",
                                title=f"Cảnh báo: {patient_name}",
                                body=cg_body,
                                metadata={"alert_id": str(alert.id)},
                                idempotency_key=f"cg_missed:{alert.id}:{link.id}",
                            )
                            created_deliveries.append(deliv.id)
            except IntegrityError:
                # Idempotent replay: this streak already raised an alert
                # (still OPEN/unresolved) on a prior scan tick.
                logger.info(
                    "Missed-dose alert already exists for patient %s (idempotent replay)",
                    patient_id,
                )
                continue

            if created_deliveries:
                try:
                    from src.modules.agents.tasks import send_notification_task

                    for d_id in created_deliveries:
                        send_notification_task.delay(str(d_id))
                except Exception as exc:
                    logger.warning("Failed to queue caregiver notification task: %s", exc)
