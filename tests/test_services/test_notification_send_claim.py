"""O-02: atomic claim before sending; transient FCM errors retry, permanent ones fail."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.fcm_service import FCMTransientError
from src.modules.adherence.models import NotificationDelivery
from src.modules.adherence.repository import NotificationRepository
from src.modules.agents.tasks import _execute_send_notification, send_notification_task
from src.modules.auth.models import UserDevice
from tests.test_services import notif_seed

PATIENT_PHONE = "+84900530001"
TOKEN = "claim-test-token-1"
FCM = "src.modules.agents.tasks.FCMService.send_push_notification"


@pytest_asyncio.fixture
async def patient_id():
    await engine.dispose()
    await notif_seed.purge([PATIENT_PHONE])
    pid = await notif_seed.create_patient(PATIENT_PHONE)
    await notif_seed.add_device(pid, TOKEN)
    yield pid
    await notif_seed.purge([PATIENT_PHONE])
    await engine.dispose()


async def _add(patient_id, *, status="QUEUED", claimed_ago=None) -> uuid.UUID:
    metadata = {}
    if claimed_ago is not None:
        metadata["claimed_at"] = (datetime.now(UTC) - claimed_ago).isoformat()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            delivery = NotificationDelivery(
                recipient_user_id=patient_id,
                channel="APP_NOTIFICATION",
                # Not DOSE_REMINDER_GROUPED: skips the dose freshness gate.
                template_code="ADHERENCE_SUGGESTION",
                title="t",
                body="b",
                scheduled_at=datetime.now(UTC),
                status=status,
                delivery_metadata=metadata,
            )
            db.add(delivery)
            await db.flush()
            return delivery.id


async def _status(delivery_id) -> str:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(NotificationDelivery.status).where(NotificationDelivery.id == delivery_id))).scalar_one()


async def _token_active() -> bool:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(UserDevice.is_active).where(UserDevice.fcm_token == TOKEN))).scalar_one()


@pytest.mark.asyncio
async def test_concurrent_claims_have_exactly_one_winner(patient_id):
    delivery_id = await _add(patient_id)

    async def claim():
        async with AsyncSessionLocal() as db:
            row = await NotificationRepository(db).claim_delivery(
                delivery_id, datetime.now(UTC), stale_sending_before=datetime.now(UTC) - timedelta(minutes=10)
            )
            await db.commit()
            return row

    results = await asyncio.gather(claim(), claim(), claim())

    assert sum(r is not None for r in results) == 1
    assert await _status(delivery_id) == "SENDING"


@pytest.mark.asyncio
async def test_a_redelivered_task_sends_only_once(patient_id):
    delivery_id = await _add(patient_id)

    with patch(FCM, return_value=(True, [])) as fcm:
        await asyncio.gather(
            _execute_send_notification(str(delivery_id)),
            _execute_send_notification(str(delivery_id)),
        )
        await _execute_send_notification(str(delivery_id))

    assert fcm.call_count == 1
    assert await _status(delivery_id) == "SENT"


@pytest.mark.asyncio
async def test_a_fresh_sending_delivery_is_left_to_the_worker_that_claimed_it(patient_id):
    delivery_id = await _add(patient_id, status="SENDING", claimed_ago=timedelta(seconds=30))

    with patch(FCM, return_value=(True, [])) as fcm:
        await _execute_send_notification(str(delivery_id))

    fcm.assert_not_called()
    assert await _status(delivery_id) == "SENDING"


@pytest.mark.asyncio
async def test_a_stale_sending_delivery_is_reclaimed_and_sent(patient_id):
    """Worker died (or hit the soft time limit) mid-send: the row must not stay stuck."""
    delivery_id = await _add(patient_id, status="SENDING", claimed_ago=timedelta(minutes=30))

    with patch(FCM, return_value=(True, [])) as fcm:
        await _execute_send_notification(str(delivery_id))

    fcm.assert_called_once()
    assert await _status(delivery_id) == "SENT"


@pytest.mark.asyncio
async def test_transient_fcm_error_marks_retrying_and_propagates(patient_id):
    delivery_id = await _add(patient_id)

    with patch(FCM, side_effect=FCMTransientError("503", dead_tokens=[])):
        with pytest.raises(FCMTransientError):
            await _execute_send_notification(str(delivery_id))

    assert await _status(delivery_id) == "RETRYING"
    assert await _token_active() is True


@pytest.mark.asyncio
async def test_a_retrying_delivery_can_be_claimed_again(patient_id):
    delivery_id = await _add(patient_id, status="RETRYING", claimed_ago=timedelta(seconds=5))

    with patch(FCM, return_value=(True, [])) as fcm:
        await _execute_send_notification(str(delivery_id))

    fcm.assert_called_once()
    assert await _status(delivery_id) == "SENT"


@pytest.mark.asyncio
async def test_transient_error_on_the_final_attempt_fails_instead_of_retrying(patient_id):
    delivery_id = await _add(patient_id)

    with patch(FCM, side_effect=FCMTransientError("503", dead_tokens=[])):
        await _execute_send_notification(str(delivery_id), final_attempt=True)

    assert await _status(delivery_id) == "FAILED"


@pytest.mark.asyncio
async def test_permanent_failure_deactivates_the_token_and_fails(patient_id):
    delivery_id = await _add(patient_id)

    with patch(FCM, return_value=(False, [TOKEN])):
        await _execute_send_notification(str(delivery_id))

    assert await _status(delivery_id) == "FAILED"
    assert await _token_active() is False


@pytest.mark.asyncio
async def test_dead_tokens_found_alongside_a_transient_error_are_still_deactivated(patient_id):
    delivery_id = await _add(patient_id)

    with patch(FCM, side_effect=FCMTransientError("503", dead_tokens=[TOKEN])):
        with pytest.raises(FCMTransientError):
            await _execute_send_notification(str(delivery_id))

    assert await _token_active() is False


def test_the_celery_task_retries_transient_errors_three_times_then_marks_final_attempt():
    calls = []

    async def fake_execute(delivery_id, *, final_attempt=False):
        calls.append(final_attempt)
        if not final_attempt:
            raise FCMTransientError("503", dead_tokens=[])

    with patch("src.modules.agents.tasks._execute_send_notification", fake_execute):
        result = send_notification_task.apply(args=[str(uuid.uuid4())])

    assert result.successful()
    assert calls == [False, False, False, True]


@pytest.mark.asyncio
async def test_soft_time_limit_mid_send_leaves_the_delivery_reclaimable(patient_id):
    """P-13: SoftTimeLimitExceeded must not strand the delivery. It stays SENDING,
    and once the claim is older than the stale threshold the next worker takes it."""
    from celery.exceptions import SoftTimeLimitExceeded

    delivery_id = await _add(patient_id)

    with patch(FCM, side_effect=SoftTimeLimitExceeded()):
        with pytest.raises(SoftTimeLimitExceeded):
            await _execute_send_notification(str(delivery_id))
    assert await _status(delivery_id) == "SENDING"

    # Pretend the claim happened 15 minutes ago (older than the 10 min threshold).
    async with AsyncSessionLocal() as db:
        async with db.begin():
            delivery = (await db.execute(select(NotificationDelivery).where(NotificationDelivery.id == delivery_id))).scalar_one()
            delivery.delivery_metadata = {"claimed_at": (datetime.now(UTC) - timedelta(minutes=15)).isoformat()}

    with patch(FCM, return_value=(True, [])) as fcm:
        await _execute_send_notification(str(delivery_id))
    fcm.assert_called_once()
    assert await _status(delivery_id) == "SENT"
