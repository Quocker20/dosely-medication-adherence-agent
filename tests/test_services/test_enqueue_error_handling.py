"""O-19: only broker/connectivity failures are swallowed around enqueue; bugs propagate."""
import logging
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError

from src.modules.adherence.notification_service import NotificationDispatchService

AT = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)


def _service():
    patient = uuid.uuid4()
    dose_repo = AsyncMock()
    dose_repo.get_due_dose_groups.return_value = {
        (patient, AT): [
            {"scheduled_dose_id": uuid.uuid4(), "medication_name": "A", "dose_value": 1, "dose_unit": "vien"}
        ]
    }
    notif_repo = AsyncMock()
    notif_repo.get_deliveries_by_idempotency_keys.return_value = {}
    notif_repo.create_grouped_delivery.side_effect = lambda **kw: (SimpleNamespace(id=uuid.uuid4()), True)
    db = MagicMock()
    db.commit = AsyncMock()
    return NotificationDispatchService(db=db, scheduled_dose_repository=dose_repo, notification_repository=notif_repo)


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [OperationalError("broker down"), RedisConnectionError("refused"), OSError("net")])
async def test_broker_failures_are_logged_with_traceback_and_do_not_abort_the_scan(exc, caplog):
    service = _service()
    with (
        patch("src.modules.agents.tasks.send_notification_task.delay", side_effect=exc),
        caplog.at_level(logging.ERROR, logger="src.modules.adherence.notification_service"),
    ):
        deliveries = await service.create_consolidated_reminders(AT)

    assert len(deliveries) == 1
    record = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_programming_errors_in_enqueue_are_not_masked():
    service = _service()
    with patch("src.modules.agents.tasks.send_notification_task.delay", side_effect=TypeError("bug")):
        with pytest.raises(TypeError):
            await service.create_consolidated_reminders(AT)
