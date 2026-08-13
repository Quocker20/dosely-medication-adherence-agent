from celery import Celery
from src.core.config import get_settings

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
)
