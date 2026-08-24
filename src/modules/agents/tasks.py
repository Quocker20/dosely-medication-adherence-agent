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
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.modules.adherence.fcm_service import FCMService
from src.modules.adherence.notification_service import NotificationDispatchService
from src.modules.adherence.repository import AlertRepository, NotificationRepository
from src.modules.agents.repository import AgentRunRepository, ScheduledDoseRepository
from src.modules.agents.service import (
    AgentRunLeaseBusyError,
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
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
    )
    try:
        async with session_factory() as session:
            service = NotificationDispatchService(
                db=session,
                scheduled_dose_repository=ScheduledDoseRepository(session),
                notification_repository=NotificationRepository(session),
            )
            await service.create_consolidated_reminders(datetime.now(timezone.utc))
    finally:
        await engine.dispose()


@celery_app.task(name="agents.scan_due_doses")
def scan_due_doses_task() -> None:
    asyncio.run(_execute_scan_due_doses())


async def _execute_send_notification(delivery_id_str: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
    )
    delivery_id = uuid.UUID(delivery_id_str)
    try:
        async with session_factory() as session:
            notif_repo = NotificationRepository(session)
            delivery = await notif_repo.get_delivery_by_id(delivery_id)
            if not delivery:
                logger.warning("Delivery %s not found for push notification", delivery_id)
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


@celery_app.task(name="agents.send_notification")
def send_notification_task(delivery_id: str) -> None:
    asyncio.run(_execute_send_notification(delivery_id))


