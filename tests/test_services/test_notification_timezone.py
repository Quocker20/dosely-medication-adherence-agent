"""O-04: reminder text uses the patient's timezone; bad timezone falls back to Vietnam time."""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.notification_service import NotificationDispatchService
from src.modules.agents.repository import ScheduledDoseRepository
from tests.test_services import notif_seed

DOSES = [{"scheduled_dose_id": uuid.uuid4(), "medication_name": "Thuoc A", "dose_value": 1, "dose_unit": "vien"}]
# 14:00 UTC == 21:00 Asia/Ho_Chi_Minh == 10:00 America/New_York (EDT)
AT = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)


def test_patient_timezone_is_used():
    title, _ = NotificationDispatchService.format_notification_text(AT, DOSES, "America/New_York")
    assert "(10:00)" in title


def test_default_is_vietnam_time():
    title, _ = NotificationDispatchService.format_notification_text(AT, DOSES)
    assert "(21:00)" in title


@pytest.mark.parametrize("bad", ["Mars/Phobos", "Not A Zone", "../../etc/passwd"])
def test_invalid_timezone_falls_back_to_vietnam_time_not_utc_and_warns(bad, caplog):
    with caplog.at_level(logging.WARNING, logger="src.modules.adherence.notification_service"):
        title, _ = NotificationDispatchService.format_notification_text(AT, DOSES, bad)
    assert "(21:00)" in title  # UTC would have printed 14:00
    assert any(r.levelno == logging.WARNING and "timezone" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.parametrize("missing", [None, ""])
def test_missing_timezone_uses_vietnam_time(missing):
    title, _ = NotificationDispatchService.format_notification_text(AT, DOSES, missing)
    assert "(21:00)" in title


@pytest.mark.asyncio
async def test_service_formats_each_group_in_its_patients_timezone():
    new_york, hanoi = uuid.uuid4(), uuid.uuid4()
    groups = {
        (new_york, AT): [{**DOSES[0], "timezone": "America/New_York"}],
        (hanoi, AT): [{**DOSES[0], "scheduled_dose_id": uuid.uuid4(), "timezone": "Asia/Ho_Chi_Minh"}],
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
        await service.create_consolidated_reminders(AT + timedelta(minutes=1))

    titles = {c.kwargs["recipient_user_id"]: c.kwargs["title"] for c in notif_repo.create_grouped_delivery.await_args_list}
    assert "(10:00)" in titles[new_york]
    assert "(21:00)" in titles[hanoi]


DOCTOR_PHONE = "+84900550001"
NY_PHONE = "+84900550002"
HN_PHONE = "+84900550003"
PHONES = [DOCTOR_PHONE, NY_PHONE, HN_PHONE]


@pytest_asyncio.fixture
async def seeded():
    await engine.dispose()
    await notif_seed.purge(PHONES)
    doctor = await notif_seed.create_doctor(DOCTOR_PHONE, "LIC-O04")
    ny = await notif_seed.create_patient(NY_PHONE, timezone="America/New_York")
    hn = await notif_seed.create_patient(HN_PHONE)
    yield doctor, ny, hn
    await notif_seed.purge(PHONES)
    await engine.dispose()


@pytest.mark.asyncio
async def test_due_groups_carry_the_patient_timezone_without_extra_queries(seeded):
    doctor, ny, hn = seeded
    now = datetime.now(UTC)
    await notif_seed.create_doses(ny, doctor, [timedelta(minutes=-5)], now=now)
    await notif_seed.create_doses(hn, doctor, [timedelta(minutes=-5)], now=now)

    async with AsyncSessionLocal() as db:
        groups = await ScheduledDoseRepository(db).get_due_dose_groups(now, not_before=now - timedelta(minutes=60))

    tz_by_patient = {patient_id: doses[0]["timezone"] for (patient_id, _), doses in groups.items()}
    assert tz_by_patient[ny] == "America/New_York"
    assert tz_by_patient[hn] == "Asia/Ho_Chi_Minh"
