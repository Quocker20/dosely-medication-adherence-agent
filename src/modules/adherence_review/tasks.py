"""Celery task entrypoint for the nightly graded-adherence review (Stage 6).

Own engine per task invocation, same reasoning as
src/modules/agents/tasks.py's module docstring: asyncpg connections bind to
the event loop that opened them, and asyncio.run() builds a fresh loop per
call, so reusing the module-level engine from src.core.database would raise
"got Future attached to a different loop" from the second run onward.
"""
import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.modules.adherence.repository import AlertRepository, NotificationRepository
from src.modules.adherence_review.repository import (
    AdherenceIndicatorRepository,
    AdherenceReviewRepository,
)
from src.modules.adherence_review.service import AdherenceReviewService

logger = logging.getLogger(__name__)


async def _execute_adherence_review_scan() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            service = AdherenceReviewService(
                db=session,
                indicator_repository=AdherenceIndicatorRepository(session),
                review_repository=AdherenceReviewRepository(session),
                alert_repository=AlertRepository(session),
                notification_repository=NotificationRepository(session),
            )
            # review_date is "today" in the run's own local calendar day,
            # matching the deployment-wide timezone the window itself is
            # computed in (compute_window_bounds) -- the Beat schedule fires
            # this at a fixed local hour (settings.adherence_review_run_hour),
            # so "now" here is already that local day.
            review_date = datetime.now(UTC).astimezone(ZoneInfo(settings.adherence_review_timezone)).date()
            stats = await service.run_nightly_review(review_date)
            logger.info("Adherence review scan for %s: %s", review_date, stats)
    finally:
        await engine.dispose()


@celery_app.task(name="adherence_review.scan")
def scan_adherence_review_task() -> None:
    asyncio.run(_execute_adherence_review_scan())
