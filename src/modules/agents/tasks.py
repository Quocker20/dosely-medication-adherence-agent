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

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.modules.adherence.repository import AlertRepository
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


async def _execute_autoschedule(
    patient_id: str, prescription_id: str | None, trigger_type: str
) -> AutoscheduleOutcome:
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
