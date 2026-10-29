"""P-08: caregiver report counts doses with one GROUP BY, not a row per dose per link."""
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.caregiver_report_service import AdherenceStats, CaregiverReportService, stats_from_counts
from src.modules.agents.repository import ScheduledDoseRepository
from tests.test_services import notif_seed

DOCTOR_PHONE = "+84900540001"
PATIENT_A = "+84900540002"
PATIENT_B = "+84900540003"
PHONES = [DOCTOR_PHONE, PATIENT_A, PATIENT_B]


def test_stats_from_counts():
    stats = stats_from_counts({"TAKEN": 3, "MISSED": 1, "SKIPPED": 1, "PENDING": 1})
    assert stats == AdherenceStats(total=6, taken=3, missed=2, rate=50.0)
    assert stats_from_counts({}).rate == 100.0


@pytest_asyncio.fixture
async def patients():
    await engine.dispose()
    await notif_seed.purge(PHONES)
    doctor = await notif_seed.create_doctor(DOCTOR_PHONE, "LIC-P08")
    a = await notif_seed.create_patient(PATIENT_A)
    b = await notif_seed.create_patient(PATIENT_B)
    yield doctor, a, b
    await notif_seed.purge(PHONES)
    await engine.dispose()


@pytest.mark.asyncio
async def test_status_counts_for_many_patients_come_from_one_grouped_query(patients):
    doctor, a, b = patients
    now = datetime.now(UTC)
    await notif_seed.create_doses(a, doctor, [timedelta(days=-1), timedelta(days=-2), timedelta(days=-30)], now=now)
    await notif_seed.create_doses(b, doctor, [timedelta(days=-1)], now=now)

    async with AsyncSessionLocal() as db:
        counts = await ScheduledDoseRepository(db).count_statuses_in_window(
            [a, b], now - timedelta(days=7), now
        )

    assert counts[a] == {"PENDING": 2}
    assert counts[b] == {"PENDING": 1}


@pytest.mark.asyncio
async def test_service_issues_one_count_query_and_one_name_query_for_n_links():
    now = datetime.now(UTC)
    links = [SimpleNamespace(id=uuid.uuid4(), patient_id=uuid.uuid4()) for _ in range(4)]
    db = MagicMock()
    db.in_transaction.return_value = False
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx

    caregivers = MagicMock()
    caregivers.claim_due_reports = AsyncMock(return_value=links)
    patients = MagicMock()
    patients.get_names_by_ids = AsyncMock(return_value={link.patient_id: "Bac An" for link in links})
    doses = MagicMock()
    doses.count_statuses_in_window = AsyncMock(
        return_value={link.patient_id: {"TAKEN": 1, "MISSED": 1} for link in links}
    )
    notifications = MagicMock()
    notifications.create_caregiver_delivery = AsyncMock(side_effect=lambda **kw: SimpleNamespace(id=uuid.uuid4()))

    service = CaregiverReportService(
        db=db,
        caregiver_repository=caregivers,
        notification_repository=notifications,
        scheduled_dose_repository=doses,
        patient_repository=patients,
    )
    ids = await service.create_due_reports(now, 7)

    assert len(ids) == 4
    assert doses.count_statuses_in_window.await_count == 1
    assert patients.get_names_by_ids.await_count == 1
    body = notifications.create_caregiver_delivery.await_args.kwargs["body"]
    assert "Tổng số liều: 2" in body
    assert "50.0%" in body
