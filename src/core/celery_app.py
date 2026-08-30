from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from src.core.config import get_settings
from src.core.firebase_app import init_firebase

settings = get_settings()

celery_app = Celery(
    "adhe_remind_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.modules.agents.tasks", "src.modules.adherence_review.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    beat_schedule={
        "scan-missed-doses": {
            "task": "agents.scan_missed_doses",
            "schedule": timedelta(minutes=settings.missed_dose_scan_interval_minutes),
        },
        "scan-due-doses": {
            "task": "agents.scan_due_doses",
            "schedule": timedelta(minutes=1),
        },
        # crontab, not a timedelta interval -- this must land at a fixed
        # local hour every night (docs/graded-adherence-implementation.md
        # Stage 6.1), not on a rolling N-minute cadence. Celery's own
        # timezone above is already Asia/Ho_Chi_Minh, matching
        # adherence_review_timezone.
        "scan-adherence-review": {
            "task": "adherence_review.scan",
            "schedule": crontab(hour=settings.adherence_review_run_hour, minute=0),
        },
        "summarize-daily-adverse-events": {
            "task": "agents.summarize_daily_adverse_events",
            "schedule": crontab(hour=22, minute=0),
        },
    },
)

@worker_process_init.connect
def init_worker(**kwargs):
    init_firebase()
