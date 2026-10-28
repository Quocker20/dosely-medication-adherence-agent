"""Celery task entrypoint for the nightly graded-adherence review (Stage 6).

Sessions come from src.core.celery_db.task_session (audit P-01): one throwaway
engine per asyncio.run, disposed afterwards.
"""
import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# Registers every ORM model module before anything below runs a query.
# Without this, an ORM operation on Alert dies with NoReferencedTableError
# the first time it needs to resolve assigned_doctor_id's target table --
# see src/core/models_registry.py and docs/adherence-review-fix-plan.md
# Defect 1.
from src.core import models_registry as _models_registry  # noqa: F401
from src.core.celery_app import celery_app
from src.core.celery_db import task_session
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
    async with task_session() as session:
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


@celery_app.task(name="adherence_review.scan")
def scan_adherence_review_task() -> None:
    asyncio.run(_execute_adherence_review_scan())
