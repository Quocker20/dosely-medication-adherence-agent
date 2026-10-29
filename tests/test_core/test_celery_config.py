"""P-13: Celery time limits, queue routing, and that the compose workers consume every queue."""
import re
from pathlib import Path

import pytest
import yaml

import src.modules.adherence_review.tasks  # noqa: F401  (registers tasks; Celery `include` is lazy)
import src.modules.agents.tasks  # noqa: F401
from src.core.celery_app import celery_app

REPO = Path(__file__).resolve().parent.parent.parent

EXPECTED_TASKS = {
    "agents.generate_schedule",
    "agents.autoschedule",
    "agents.scan_missed_doses",
    "agents.scan_due_doses",
    "agents.summarize_daily_adverse_events",
    "agents.send_notification",
    "agents.send_caregiver_adherence_reports",
    "adherence_review.scan",
}


def _registered():
    return {n for n in celery_app.tasks if not n.startswith("celery.")}


def test_the_task_registry_is_unchanged():
    assert _registered() == EXPECTED_TASKS


def test_normal_tasks_have_default_soft_and_hard_limits():
    conf = celery_app.conf
    assert conf.task_soft_time_limit == 120
    assert conf.task_time_limit == 180
    for name in EXPECTED_TASKS - {"adherence_review.scan"}:
        task = celery_app.tasks[name]
        # None means "inherit the conf default" (what the worker does); an
        # explicit per-task value must not loosen it.
        assert task.soft_time_limit in (None, 120) and task.time_limit in (None, 180), name


def test_the_review_task_has_its_own_larger_limits_for_a_100_minute_worst_case():
    task = celery_app.tasks["adherence_review.scan"]
    assert task.soft_time_limit == 6000
    assert task.time_limit == 6600
    assert task.soft_time_limit >= 100 * 60


def test_review_is_not_acks_late_so_the_redis_visibility_timeout_cannot_redeliver_it():
    """A late-acked 100-minute task would be redelivered after Redis's default
    1h visibility timeout and run twice concurrently."""
    assert celery_app.tasks["adherence_review.scan"].acks_late is False


def test_worker_settings():
    conf = celery_app.conf
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_acks_late is True


def _queue_for(task_name: str) -> str:
    route = celery_app.amqp.router.route({}, task_name)
    return route["queue"].name


def test_every_task_has_an_explicit_queue():
    assert _queue_for("adherence_review.scan") == "review"
    for name in ("agents.scan_due_doses", "agents.send_notification", "agents.send_caregiver_adherence_reports"):
        assert _queue_for(name) == "notifications"
    for name in ("agents.generate_schedule", "agents.autoschedule", "agents.scan_missed_doses", "agents.summarize_daily_adverse_events"):
        assert _queue_for(name) == "celery"


def test_beat_entries_target_registered_tasks():
    for entry in celery_app.conf.beat_schedule.values():
        assert entry["task"] in EXPECTED_TASKS


def _worker_queues() -> dict[str, set[str]]:
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    result = {}
    for name, service in compose["services"].items():
        command = service.get("command")
        if isinstance(command, list):
            command = " ".join(command)
        if command and "celery" in command and " worker" in command:
            match = re.search(r"(?:-Q|--queues)[= ]\s*(\S+)", command)
            assert match, f"worker service {name} must pass -Q explicitly"
            result[name] = set(match.group(1).split(","))
    return result


def test_compose_workers_consume_every_routed_queue():
    workers = _worker_queues()
    consumed = set().union(*workers.values())
    routed = {_queue_for(n) for n in EXPECTED_TASKS}
    assert routed <= consumed, f"queues with no consumer: {routed - consumed}"


def test_review_queue_is_isolated_from_the_reminder_worker():
    """A 100-minute LLM job must never occupy a slot of the worker that sends reminders."""
    workers = _worker_queues()
    for name, queues in workers.items():
        if "review" in queues:
            assert queues == {"review"}, name
        else:
            assert {"celery", "notifications"} <= queues, name


@pytest.mark.parametrize("service", ["worker-review"])
def test_review_worker_runs_one_job_at_a_time(service):
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    command = compose["services"][service]["command"]
    command = " ".join(command) if isinstance(command, list) else command
    assert re.search(r"--concurrency[= ]1\b", command)
