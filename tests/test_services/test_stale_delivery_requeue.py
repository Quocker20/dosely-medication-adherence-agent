"""O-01: deliveries orphaned by a lost enqueue or a dead worker are re-enqueued."""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.notification_service import NotificationDispatchService
from src.modules.adherence.repository import NotificationRepository
from tests.test_services import notif_seed

PATIENT_PHONE = "+84900520001"
NOW = datetime.now(UTC)


@pytest_asyncio.fixture
async def patient_id():
    await engine.dispose()
    await notif_seed.purge([PATIENT_PHONE])
    pid = await notif_seed.create_patient(PATIENT_PHONE)
    yield pid
    await notif_seed.purge([PATIENT_PHONE])
    await engine.dispose()


async def _add(patient_id, *, status, age, claimed_ago=None, template="DOSE_REMINDER_GROUPED") -> uuid.UUID:
    metadata = {}
    if claimed_ago is not None:
        metadata["claimed_at"] = (NOW - claimed_ago).isoformat()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            delivery = NotificationDelivery(
                recipient_user_id=patient_id,
                channel="APP_NOTIFICATION",
                template_code=template,
                title="t",
                body="b",
                scheduled_at=NOW - age,
                status=status,
                delivery_metadata=metadata,
                created_at=NOW - age,
            )
            db.add(delivery)
            await db.flush()
            return delivery.id


async def _scan(patient_id: uuid.UUID) -> set[str]:
    """Ids this scan enqueued for the test patient (the scan itself is table-wide,
    so rows other test modules left behind are filtered out)."""
    async with AsyncSessionLocal() as db:
        service = NotificationDispatchService(
            db=db, scheduled_dose_repository=None, notification_repository=NotificationRepository(db)
        )
        with patch("src.modules.agents.tasks.send_notification_task.delay") as delay:
            await service.requeue_stale_deliveries(NOW)
    enqueued = {call.args[0] for call in delay.call_args_list}
    async with AsyncSessionLocal() as db:
        mine = (
            await db.execute(select(NotificationDelivery.id).where(NotificationDelivery.recipient_user_id == patient_id))
        ).scalars().all()
    return enqueued & {str(i) for i in mine}


@pytest.mark.asyncio
async def test_old_queued_and_stuck_sending_are_requeued_but_fresh_or_final_are_not(patient_id):
    stale_queued = await _add(patient_id, status="QUEUED", age=timedelta(minutes=5))
    fresh_queued = await _add(patient_id, status="QUEUED", age=timedelta(seconds=30))
    stuck_sending = await _add(patient_id, status="SENDING", age=timedelta(minutes=30), claimed_ago=timedelta(minutes=15))
    live_sending = await _add(patient_id, status="SENDING", age=timedelta(minutes=30), claimed_ago=timedelta(minutes=1))
    stuck_retrying = await _add(patient_id, status="RETRYING", age=timedelta(minutes=30), claimed_ago=timedelta(minutes=20))
    sent = await _add(patient_id, status="SENT", age=timedelta(hours=1))
    ancient = await _add(patient_id, status="QUEUED", age=timedelta(days=3))

    enqueued = await _scan(patient_id)

    assert enqueued == {str(stale_queued), str(stuck_sending), str(stuck_retrying)}
    for ignored in (fresh_queued, live_sending, sent, ancient):
        assert str(ignored) not in enqueued


@pytest.mark.asyncio
async def test_requeue_is_not_repeated_on_the_very_next_scan(patient_id):
    """A backed-up queue must not collect one duplicate task per minute."""
    delivery_id = await _add(patient_id, status="QUEUED", age=timedelta(minutes=5))

    first = await _scan(patient_id)
    second = await _scan(patient_id)

    assert first == {str(delivery_id)}
    assert second == set()
