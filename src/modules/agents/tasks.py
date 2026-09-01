"""Celery task entrypoints for slice 6 schedule generation/reschedule.

asyncpg connections bind to the event loop that opened them. celery_app's
worker runs each task synchronously and asyncio.run() builds a fresh event
loop per call, so reusing the module-level engine/sessionmaker from
src.core.database (built against the *import-time* loop) raises
"got Future attached to a different loop" from the second task onward. Each
task therefore builds its own engine with poolclass=NullPool inside the
coroutine and disposes it in a finally — pooling buys nothing for a single
connection doing one task anyway.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select, update
from sqlalchemy.pool import NullPool

from src.core.celery_app import celery_app
from src.core.config import get_settings

# Registers every ORM model module before anything below runs a query.
# Without this, an ORM operation on Alert dies with NoReferencedTableError
# the first time it needs to resolve assigned_doctor_id's target table --
# see src/core/models_registry.py and docs/adherence-review-fix-plan.md
# Defect 1/5.
from src.core import models_registry as _models_registry  # noqa: F401
from src.modules.adherence.fcm_service import FCMService
from src.modules.adherence.notification_service import DOSE_REMINDER_TEMPLATE_CODE, NotificationDispatchService
from src.modules.adherence.repository import AlertRepository, NotificationRepository
from src.modules.adherence.models import SuspectedAdverseEvent
from src.modules.agents.repository import AgentRunRepository, ScheduledDoseRepository
from src.modules.agents.service import (
    AgentRunLeaseBusyError,
    AutoscheduleOutcome,
    MissedDoseScanService,
    SchedulingService,
)

logger = logging.getLogger(__name__)


async def _execute(run_id: str, patient_id: str, is_reschedule: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            service = SchedulingService(
                db=session,
                agent_run_repository=AgentRunRepository(session),
                scheduled_dose_repository=ScheduledDoseRepository(session),
            )
            # Keep the old task signature for queued messages, but derive
            # patient and run type exclusively from the atomically claimed DB row.
            await service.execute_run(run_id=uuid.UUID(run_id))
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="agents.generate_schedule",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=5,
)
def generate_schedule_task(self, run_id: str, patient_id: str, is_reschedule: bool) -> None:
    try:
        asyncio.run(_execute(run_id, patient_id, is_reschedule))
    except AgentRunLeaseBusyError as exc:
        # A worker-lost redelivery can arrive before the old lease expires.
        # Retry after one lease window so claim_run can reclaim it safely.
        raise self.retry(
            exc=exc,
            countdown=get_settings().planning_run_lease_seconds,
        ) from exc


async def _execute_autoschedule(patient_id: str, prescription_id: str | None, trigger_type: str) -> AutoscheduleOutcome:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            service = SchedulingService(
                db=session,
                agent_run_repository=AgentRunRepository(session),
                scheduled_dose_repository=ScheduledDoseRepository(session),
            )
            return await service.request_autoschedule(
                patient_id=uuid.UUID(patient_id),
                prescription_id=uuid.UUID(prescription_id) if prescription_id else None,
                trigger_type=trigger_type,
            )
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="agents.autoschedule")
def autoschedule_task(self, patient_id: str, prescription_id: str | None, trigger_type: str) -> None:
    """Plan (or replan) after a prescription approval or a routine change.

    Separate from generate_schedule_task because this one has to create the
    AgentRun itself, and creating it can lose a race against
    uq_agent_runs_one_running. Dropping the message there would leave the
    patient without reminders for the drug that was just approved, so a busy
    patient is retried rather than swallowed.
    """
    settings = get_settings()
    outcome = asyncio.run(_execute_autoschedule(patient_id, prescription_id, trigger_type))
    if outcome is AutoscheduleOutcome.RUN_IN_FLIGHT:
        raise self.retry(
            countdown=settings.prescription_autoschedule_retry_seconds,
            max_retries=settings.prescription_autoschedule_max_retries,
        )


async def _execute_missed_dose_scan() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            service = MissedDoseScanService(
                db=session,
                scheduled_dose_repository=ScheduledDoseRepository(session),
                alert_repository=AlertRepository(session),
            )
            await service.run_scan()
    finally:
        await engine.dispose()


@celery_app.task(name="agents.scan_missed_doses")
def scan_missed_doses_task() -> None:
    asyncio.run(_execute_missed_dose_scan())


async def _execute_scan_due_doses() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            service = NotificationDispatchService(
                db=session,
                scheduled_dose_repository=ScheduledDoseRepository(session),
                notification_repository=NotificationRepository(session),
            )
            await service.create_consolidated_reminders(datetime.now(UTC))
    finally:
        await engine.dispose()


@celery_app.task(name="agents.scan_due_doses")
def scan_due_doses_task() -> None:
    asyncio.run(_execute_scan_due_doses())


async def _execute_daily_adverse_event_summary() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                rows = list((await session.execute(
                    select(SuspectedAdverseEvent).where(
                        SuspectedAdverseEvent.daily_notified_at.is_(None),
                        SuspectedAdverseEvent.review_status == "NEW",
                        SuspectedAdverseEvent.risk_level.in_(["LOW", "MODERATE"]),
                        SuspectedAdverseEvent.reported_at >= datetime.now(timezone.utc) - timedelta(hours=24),
                    ).order_by(SuspectedAdverseEvent.patient_id, SuspectedAdverseEvent.reported_at)
                )).scalars().all())
                grouped: dict[uuid.UUID, list[SuspectedAdverseEvent]] = {}
                for row in rows: grouped.setdefault(row.patient_id, []).append(row)
                now = datetime.now(timezone.utc)
                for patient_id, events in grouped.items():
                    names = sorted({str(s.get("name")) for event in events for s in event.symptoms if s.get("name")})
                    alert = await AlertRepository(session).create_alert(
                        patient_id=patient_id, triggered_by_type="ADVERSE_EVENT",
                        alert_type="SUSPECTED_ADVERSE_EVENT", severity="MEDIUM",
                        message=f"Tổng hợp {len(events)} ghi nhận triệu chứng trong ngày: {', '.join(names)}",
                        metadata={"adverse_event_ids": [str(event.id) for event in events], "symptoms": names, "summary_type": "DAILY"},
                    )
                    await session.execute(update(SuspectedAdverseEvent).where(
                        SuspectedAdverseEvent.id.in_([event.id for event in events])
                    ).values(daily_notified_at=now, alert_id=alert.id))
    finally:
        await engine.dispose()


@celery_app.task(name="agents.summarize_daily_adverse_events")
def summarize_daily_adverse_events_task() -> None:
    asyncio.run(_execute_daily_adverse_event_summary())


async def _execute_send_notification(delivery_id_str: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    delivery_id = uuid.UUID(delivery_id_str)
    try:
        async with session_factory() as session:
            notif_repo = NotificationRepository(session)
            delivery = await notif_repo.get_delivery_by_id(delivery_id)
            if not delivery:
                logger.warning("Delivery %s not found for notification", delivery_id)
                return

            # Celery is at-least-once; a redelivered task must not push twice.
            if delivery.status not in ("QUEUED", "RETRYING"):
                logger.info("Delivery %s already in status %s; skipping send", delivery_id, delivery.status)
                return

            # ── 1. Telegram / Caregiver Delivery Branch ───────────────────
            if delivery.channel == "TELEGRAM" or delivery.caregiver_link_id is not None:
                from src.core.telegram import (
                    TelegramBlockedError,
                    TelegramPermanentError,
                    TelegramRateLimitError,
                    TelegramTransientError,
                    get_telegram_client,
                )
                from src.modules.caregivers.repository import CaregiverRepository

                cg_repo = CaregiverRepository(session)
                link = (
                    await cg_repo.get_link_by_id(delivery.caregiver_link_id)
                    if delivery.caregiver_link_id
                    else None
                )

                if not link or link.status != "ACTIVE" or not link.telegram_chat_id:
                    logger.info(
                        "Caregiver link %s not active or missing telegram_chat_id; failing delivery",
                        delivery.caregiver_link_id,
                    )
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="FAILED",
                        error_message="Caregiver link is not active or bound",
                    )
                    await session.commit()
                    return

                if not settings.telegram_enabled:
                    logger.info("Telegram disabled; marking delivery %s as DELIVERED (mock)", delivery.id)
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="DELIVERED",
                        provider_message_id="mock-telegram-disabled",
                    )
                    await session.commit()
                    return

                tg_client = get_telegram_client()
                try:
                    msg_id = await tg_client.send_message(
                        chat_id=link.telegram_chat_id,
                        text=delivery.body,
                    )
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="DELIVERED",
                        provider_message_id=str(msg_id),
                    )
                    await cg_repo.update_last_message_sent(link.id, datetime.now(timezone.utc))
                    await session.commit()
                except TelegramBlockedError as exc:
                    logger.warning("Caregiver chat %s blocked bot: %s", link.telegram_chat_id, exc)
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="BLOCKED_BY_USER",
                        error_message=str(exc),
                    )
                    await cg_repo.mark_blocked(link.telegram_chat_id)
                    await session.commit()
                except TelegramPermanentError as exc:
                    logger.warning("Permanent error sending Telegram message: %s", exc)
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="FAILED",
                        error_message=str(exc),
                    )
                    await session.commit()
                except TelegramRateLimitError as exc:
                    logger.warning("Telegram rate limit hit (retry_after=%s): %s", exc.retry_after, exc)
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="RETRYING",
                        error_message=str(exc),
                    )
                    await session.commit()
                    raise exc
                except TelegramTransientError as exc:
                    logger.warning("Transient error contacting Telegram: %s", exc)
                    await notif_repo.update_delivery_result(
                        delivery.id,
                        status="RETRYING",
                        error_message=str(exc),
                    )
                    await session.commit()
                    raise exc
                return

            # ── 2. Patient FCM Push Notification Branch ────────────────────
            # Freshness gate for dose reminders only. Alert/SOS deliveries
            # carry no doses and must never be held back by this.
            if delivery.template_code == DOSE_REMINDER_TEMPLATE_CODE:
                linked, still_due = await notif_repo.count_reminder_doses(delivery.id, delivery.scheduled_at)
                if linked == 0 or still_due != linked:
                    logger.info(
                        "Delivery %s superseded: %d of %d linked doses still due at %s",
                        delivery_id,
                        still_due,
                        linked,
                        delivery.scheduled_at.isoformat(),
                    )
                    await notif_repo.update_delivery_status(delivery.id, "SUPERSEDED")
                    await session.commit()
                    return

            tokens = await notif_repo.get_active_fcm_tokens(delivery.recipient_user_id)
            if tokens:
                success, dead_tokens = FCMService.send_push_notification(
                    tokens=tokens,
                    title=delivery.title,
                    body=delivery.body,
                    data={
                        "delivery_id": str(delivery.id),
                        "action": "dose_reminder",
                    },
                )
                if dead_tokens:
                    logger.info("Deactivating %d expired/unregistered FCM token(s)", len(dead_tokens))
                    await notif_repo.deactivate_fcm_tokens(dead_tokens)

                status = "SENT" if success else "FAILED"
            else:
                logger.info(
                    "Recipient user %s has no active FCM device tokens; marked as NO_DEVICE.",
                    delivery.recipient_user_id,
                )
                status = "NO_DEVICE"

            await notif_repo.update_delivery_status(delivery.id, status)
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="agents.send_notification",
    max_retries=3,
    default_retry_delay=5,
)
def send_notification_task(self, delivery_id: str) -> None:
    from src.core.telegram import TelegramRateLimitError, TelegramTransientError

    try:
        asyncio.run(_execute_send_notification(delivery_id))
    except TelegramRateLimitError as exc:
        countdown = exc.retry_after if exc.retry_after is not None else 10
        raise self.retry(exc=exc, countdown=countdown) from exc
    except TelegramTransientError as exc:
        raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries)) from exc


async def _execute_send_caregiver_adherence_reports() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    now = datetime.now(timezone.utc)
    interval_days = settings.caregiver_report_interval_days

    try:
        async with session_factory() as session:
            from src.modules.adherence.repository import NotificationRepository
            from src.modules.agents.models import ScheduledDose
            from src.modules.caregivers.repository import CaregiverRepository
            from src.modules.patients.models import PatientProfile

            cg_repo = CaregiverRepository(session)
            async with session.begin():
                claimed_links = await cg_repo.claim_due_reports(now, interval_days)

            if not claimed_links:
                logger.info("No caregiver links due for adherence report at %s", now.isoformat())
                return

            notif_repo = NotificationRepository(session)
            delivery_ids: list[uuid.UUID] = []

            for link in claimed_links:
                start_date = now - timedelta(days=interval_days)

                p_stmt = select(PatientProfile.name).where(PatientProfile.user_id == link.patient_id)
                patient_name = (await session.execute(p_stmt)).scalar_one_or_none() or "Người bệnh"

                doses_stmt = select(ScheduledDose.status).where(
                    ScheduledDose.patient_id == link.patient_id,
                    ScheduledDose.current_scheduled_at >= start_date,
                    ScheduledDose.current_scheduled_at <= now,
                )
                statuses = list((await session.execute(doses_stmt)).scalars().all())
                total = len(statuses)
                taken = sum(1 for s in statuses if s == "TAKEN")
                missed = sum(1 for s in statuses if s in ("MISSED", "SKIPPED"))
                rate = (taken / total * 100.0) if total > 0 else 100.0

                body = (
                    f"Báo cáo tuân thủ dùng thuốc định kỳ ({interval_days} ngày qua)\n"
                    f"Người bệnh: {patient_name}\n"
                    f"• Tổng số liều: {total}\n"
                    f"• Đã uống: {taken}\n"
                    f"• Quên/Bỏ lỡ: {missed}\n"
                    f"• Tỷ lệ tuân thủ: {rate:.1f}%\n\n"
                    f"Cảm ơn bạn đã đồng hành chăm sóc sức khỏe cùng RemindRx."
                )

                if session.in_transaction():
                    await session.commit()

                async with session.begin():
                    delivery = await notif_repo.create_caregiver_delivery(
                        caregiver_link_id=link.id,
                        template_code="CG_REPORT",
                        title=f"Báo cáo tuân thủ {patient_name}",
                        body=body,
                        metadata={
                            "patient_id": str(link.patient_id),
                            "interval_days": interval_days,
                            "total_doses": total,
                            "taken_doses": taken,
                            "missed_doses": missed,
                            "adherence_rate": rate,
                        },
                    )
                    delivery_ids.append(delivery.id)

            for d_id in delivery_ids:
                send_notification_task.delay(str(d_id))
    finally:
        await engine.dispose()


@celery_app.task(name="agents.send_caregiver_adherence_reports")
def send_caregiver_adherence_reports_task() -> None:
    asyncio.run(_execute_send_caregiver_adherence_reports())
