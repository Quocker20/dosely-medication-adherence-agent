from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init

from src.core.config import get_settings
from src.core.firebase_app import init_firebase

settings = get_settings()

celery_app = Celery(
    "adhe_remind_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.modules.agents.tasks"],
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
    },
)

@worker_process_init.connect
def init_worker(**kwargs):
    init_firebase()
