"""P-02: the due-dose scan is bounded below and does one idempotency query."""
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.notification_service import NotificationDispatchService
from src.modules.agents.repository import ScheduledDoseRepository
from tests.test_services import notif_seed

DOCTOR_PHONE = "+84900510001"
PATIENT_PHONE = "+84900510002"
PHONES = [DOCTOR_PHONE, PATIENT_PHONE]


@pytest_asyncio.fixture
async def seeded():
    await engine.dispose()
    await notif_seed.purge(PHONES)
    doctor_id = await notif_seed.create_doctor(DOCTOR_PHONE, "LIC-P02")
    patient_id = await notif_seed.create_patient(PATIENT_PHONE)
    yield doctor_id, patient_id
    await notif_seed.purge(PHONES)
    await engine.dispose()


@pytest.mark.asyncio
async def test_doses_older_than_the_missed_window_are_left_to_the_missed_scan(seeded):
    doctor_id, patient_id = seeded
    now = datetime.now(UTC)
    overdue = get_settings().missed_dose_overdue_minutes
    await notif_seed.create_doses(
        patient_id,
        doctor_id,
        [timedelta(minutes=-5), timedelta(minutes=-(overdue + 30)), timedelta(hours=-6)],
        now=now,
    )

    async with AsyncSessionLocal() as db:
        groups = await ScheduledDoseRepository(db).get_due_dose_groups(
            now, not_before=now - timedelta(minutes=overdue)
        )

    scheduled_ats = [at for (_, at) in groups]
    assert len(scheduled_ats) == 1
    assert all(at >= now - timedelta(minutes=overdue) for at in scheduled_ats)


@pytest.mark.asyncio
async def test_service_bounds_the_query_by_the_missed_dose_overdue_window():
    cutoff = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    dose_repo = AsyncMock()
    dose_repo.get_due_dose_groups.return_value = {}
    service = NotificationDispatchService(
        db=MagicMock(), scheduled_dose_repository=dose_repo, notification_repository=AsyncMock()
    )

    await service.create_consolidated_reminders(cutoff)

    dose_repo.get_due_dose_groups.assert_awaited_once_with(
        cutoff, not_before=cutoff - timedelta(minutes=get_settings().missed_dose_overdue_minutes)
    )


@pytest.mark.asyncio
async def test_idempotency_lookup_is_one_batched_query_for_n_groups():
    cutoff = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    groups = {
        (uuid.uuid4(), cutoff - timedelta(minutes=i)): [
            {"scheduled_dose_id": uuid.uuid4(), "medication_name": "A", "dose_value": 1, "dose_unit": "vien"}
        ]
        for i in range(5)
    }
    dose_repo = AsyncMock()
    dose_repo.get_due_dose_groups.return_value = groups
    notif_repo = AsyncMock()
    notif_repo.get_deliveries_by_idempotency_keys.return_value = {}
    notif_repo.create_grouped_delivery.side_effect = lambda **kw: (SimpleNamespace(id=uuid.uuid4()), True)
    db = MagicMock()
    db.commit = AsyncMock()
    service = NotificationDispatchService(db=db, scheduled_dose_repository=dose_repo, notification_repository=notif_repo)

    with patch("src.modules.agents.tasks.send_notification_task.delay"):
        await service.create_consolidated_reminders(cutoff)

    notif_repo.get_deliveries_by_idempotency_keys.assert_awaited_once()
    assert len(notif_repo.get_deliveries_by_idempotency_keys.await_args.args[0]) == 5
    notif_repo.get_delivery_by_idempotency_key.assert_not_awaited()
    assert notif_repo.create_grouped_delivery.await_count == 5
