from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, worker_process_init

from src.core.config import get_settings
from src.core.firebase_app import init_firebase
from src.core.logging_config import configure_logging

settings = get_settings()

# Celery's built-in default queue name: kept so messages already in Redis still drain.
QUEUE_DEFAULT = "celery"
QUEUE_NOTIFICATIONS = "notifications"
QUEUE_REVIEW = "review"

celery_app = Celery(
    "dosely_tasks",
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
    # P-13: no task may hang a worker slot forever. Soft limit raises
    # SoftTimeLimitExceeded inside the task; the hard limit kills the child.
    # A send_notification killed this way leaves its delivery SENDING, which
    # the scan re-claims after notification_sending_stale_minutes (10 min, well
    # above the 180 s hard limit).
    task_soft_time_limit=120,
    task_time_limit=180,
    # One task at a time per process, acked after it finishes. Safe because
    # every task here is idempotent (send_notification is claim-guarded).
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Queues (P-13). The review job (LLM, up to ~100 min) is isolated so it can
    # never occupy a slot that sends reminders. Every queue below MUST be
    # listed in a worker's -Q in docker-compose.yml, or its tasks are never run.
    task_default_queue=QUEUE_DEFAULT,
    task_routes={
        "agents.scan_due_doses": {"queue": QUEUE_NOTIFICATIONS},
        "agents.send_notification": {"queue": QUEUE_NOTIFICATIONS},
        "agents.send_caregiver_adherence_reports": {"queue": QUEUE_NOTIFICATIONS},
        "adherence_review.scan": {"queue": QUEUE_REVIEW},
    },
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
        "send-caregiver-adherence-reports": {
            "task": "agents.send_caregiver_adherence_reports",
            "schedule": crontab(hour=8, minute=0),
        },
    },
)

@setup_logging.connect
def init_logging(**kwargs):
    # Connecting to setup_logging stops Celery from configuring logging itself, so
    # LOG_LEVEL (not the --loglevel CLI flag) governs the worker and beat.
    configure_logging(settings.log_level)


@worker_process_init.connect
def init_worker(**kwargs):
    init_firebase()
