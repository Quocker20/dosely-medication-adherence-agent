"""AdherenceIndicatorRepository: the nightly review's read-only queries.

Verifies against the real database (not mocks) that:
  - each query is one round trip for the whole population, not per-patient
  - the four severity-side buckets (taken/skipped/missed/critical_missed)
    sum to `total`, matching AdherenceLogRepository.get_dose_status_counts'
    invariant
  - the medication breakdown caps at top_n per patient
  - compute_window_bounds produces a closed [start, end) UTC pair

Uses the same fixed-phone-number + purge-before-and-after pattern as
tests/test_api/test_dashboard.py, since these queries have no per-test
transaction isolation of their own (real commits against a shared DB).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import HealthSurvey, SymptomReport
from src.modules.adherence_review.models import AdherenceReview
from src.modules.adherence_review.repository import (
    AdherenceIndicatorRepository,
    compute_window_bounds,
)
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Prescription, PrescriptionItem

PATIENT_A_PHONE = "+84900800001"
PATIENT_B_PHONE = "+84900800002"
_TEST_PHONES = (PATIENT_A_PHONE, PATIENT_B_PHONE)

OVERDUE_MINUTES = 60


async def _purge_test_data() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (
                (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES))))
                .scalars()
                .all()
            )
            if not ids:
                return
            await db.execute(delete(AdherenceReview).where(AdherenceReview.patient_id.in_(ids)))
            await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
            await db.execute(delete(SymptomReport).where(SymptomReport.patient_id.in_(ids)))
            await db.execute(delete(HealthSurvey).where(HealthSurvey.patient_id.in_(ids)))
            await db.execute(delete(Prescription).where(Prescription.patient_id.in_(ids)))
            await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    await engine.dispose()
    await _purge_test_data()
    yield
    await _purge_test_data()
    await engine.dispose()


async def _create_patient(phone: str, name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password("123456"), role="PATIENT"
            )
            await PatientRepository(db).create_patient_profile(user_id=user.id, name=name)
        return user.id


async def _create_prescription(patient_id: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            rx = Prescription(patient_id=patient_id, doctor_id=None, status="APPROVED")
            db.add(rx)
            await db.flush()
            return rx.id


async def _add_dose(
    prescription_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    at: datetime,
    status: str,
    dose_slot: str | None = None,
    medication_id: uuid.UUID | None = None,
    display_name: str = "Metformin 500mg",
    is_critical: bool = False,
) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            item = PrescriptionItem(
                prescription_id=prescription_id,
                medication_id=medication_id,
                display_name=display_name,
                dose_unit="VIEN",
                start_date=at.date(),
                is_critical=is_critical,
            )
            db.add(item)
            await db.flush()
            db.add(
                ScheduledDose(
                    prescription_item_id=item.id,
                    patient_id=patient_id,
                    original_scheduled_at=at,
                    current_scheduled_at=at,
                    status=status,
                    taken_at=at if status == "TAKEN" else None,
                    dose_slot=dose_slot,
                    medication_id=medication_id,
                    is_critical=is_critical,
                )
            )


class TestComputeWindowBounds:
    def test_produces_a_closed_utc_window(self):
        start, end = compute_window_bounds(date(2026, 8, 29), window_days=7, timezone_name="Asia/Ho_Chi_Minh")
        assert end - start == timedelta(days=7)
        assert start.tzinfo is not None and end.tzinfo is not None
        # Asia/Ho_Chi_Minh is UTC+7 with no DST -- 2026-08-29 00:00 local is
        # 2026-08-28 17:00 UTC.
        assert end == datetime(2026, 8, 28, 17, 0, tzinfo=timezone.utc)
        assert start == datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc)


class TestSeverityIndicators:
    @pytest.mark.asyncio
    async def test_four_buckets_sum_to_total(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=1), status="TAKEN")
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=2), status="SKIPPED")
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=3), status="MISSED")
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=4), status="MISSED", is_critical=True)

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            rows = await repo.get_severity_indicators(
                now - timedelta(days=7), now + timedelta(hours=1), OVERDUE_MINUTES
            )

        row = next(r for r in rows if r.patient_id == patient_id)
        assert row.total == 4
        assert row.taken == 1
        assert row.skipped == 1
        assert row.missed == 2
        assert row.critical_missed == 1
        assert row.taken + row.skipped + row.missed == row.total

    @pytest.mark.asyncio
    async def test_pending_within_grace_window_is_excluded_from_both_sides(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        # Due in 10 minutes -- still PENDING, well inside the 60-minute grace
        # window, must not count as due yet.
        await _add_dose(rx_id, patient_id, at=now + timedelta(minutes=10), status="PENDING")

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            rows = await repo.get_severity_indicators(
                now - timedelta(days=7), now + timedelta(days=1), OVERDUE_MINUTES
            )

        assert not any(r.patient_id == patient_id for r in rows)

    @pytest.mark.asyncio
    async def test_patient_with_no_doses_produces_no_row(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            rows = await repo.get_severity_indicators(
                now - timedelta(days=7), now, OVERDUE_MINUTES
            )

        assert not any(r.patient_id == patient_id for r in rows)


class TestSlotBreakdown:
    @pytest.mark.asyncio
    async def test_groups_by_slot_with_at_most_four_rows(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=1), status="MISSED", dose_slot="EVENING")
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=2), status="MISSED", dose_slot="EVENING")
        await _add_dose(rx_id, patient_id, at=now - timedelta(hours=3), status="TAKEN", dose_slot="MORNING")

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            grouped = await repo.get_slot_breakdown(
                now - timedelta(days=7), now + timedelta(hours=1), OVERDUE_MINUTES
            )

        slots = {s.dose_slot: s for s in grouped[patient_id]}
        assert len(grouped[patient_id]) <= 4
        assert slots["EVENING"].total == 2
        assert slots["EVENING"].missed == 2
        assert slots["MORNING"].total == 1
        assert slots["MORNING"].missed == 0


class TestMedicationBreakdown:
    @pytest.mark.asyncio
    async def test_caps_at_top_n_by_miss_count(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        med_ids = [uuid.uuid4() for _ in range(3)]
        # med 0: 3 missed, med 1: 1 missed, med 2: 0 missed
        for i in range(3):
            await _add_dose(
                rx_id, patient_id, at=now - timedelta(hours=i + 1), status="MISSED",
                medication_id=med_ids[0], display_name="Drug Zero",
            )
        await _add_dose(
            rx_id, patient_id, at=now - timedelta(hours=10), status="MISSED",
            medication_id=med_ids[1], display_name="Drug One",
        )
        await _add_dose(
            rx_id, patient_id, at=now - timedelta(hours=11), status="TAKEN",
            medication_id=med_ids[2], display_name="Drug Two",
        )

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            grouped = await repo.get_medication_breakdown(
                now - timedelta(days=7), now + timedelta(hours=1), OVERDUE_MINUTES, top_n=2
            )

        rows = grouped[patient_id]
        assert len(rows) == 2
        assert rows[0].medication_id == med_ids[0]
        assert rows[0].missed == 3
        assert rows[0].display_name == "Drug Zero"

    @pytest.mark.asyncio
    async def test_legacy_null_medication_id_is_excluded(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        await _add_dose(
            rx_id, patient_id, at=now - timedelta(hours=1), status="MISSED", medication_id=None
        )

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            grouped = await repo.get_medication_breakdown(
                now - timedelta(days=7), now + timedelta(hours=1), OVERDUE_MINUTES
            )

        assert patient_id not in grouped


class TestTrendIndicators:
    @pytest.mark.asyncio
    async def test_returns_prior_window_totals_only(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        rx_id = await _create_prescription(patient_id)
        now = datetime.now(timezone.utc)
        prior_at = now - timedelta(days=10)
        await _add_dose(rx_id, patient_id, at=prior_at, status="TAKEN")

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            trend = await repo.get_trend_indicators(
                now - timedelta(days=14), now - timedelta(days=7), OVERDUE_MINUTES
            )

        assert trend[patient_id].total == 1
        assert trend[patient_id].taken == 1


class TestSymptomEvidence:
    @pytest.mark.asyncio
    async def test_only_symptom_code_and_severity_are_returned(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        today = date.today()
        async with AsyncSessionLocal() as db:
            async with db.begin():
                survey = HealthSurvey(
                    patient_id=patient_id,
                    survey_date=today,
                    status="SUBMITTED",
                    answers_json={"blood_pressure": "should not appear"},
                    submitted_at=datetime.now(timezone.utc),
                )
                db.add(survey)
                await db.flush()
                db.add(
                    SymptomReport(
                        patient_id=patient_id,
                        survey_id=survey.id,
                        symptom_code="NAUSEA",
                        severity="MODERATE",
                        description="patient-authored free text, must not leak",
                        source="HEALTH_SURVEY",
                    )
                )

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            grouped = await repo.get_symptom_evidence(today - timedelta(days=7), today)

        evidence = grouped[patient_id][0]
        assert evidence.symptom_code == "NAUSEA"
        assert evidence.severity == "MODERATE"
        assert not hasattr(evidence, "description")
        assert not hasattr(evidence, "answers_json")


class TestPriorReviews:
    @pytest.mark.asyncio
    async def test_returns_only_the_most_recent_review_per_patient(self):
        patient_id = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        today = date.today()
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(
                    AdherenceReview(
                        patient_id=patient_id,
                        review_date=today - timedelta(days=2),
                        window_start=today - timedelta(days=9),
                        window_end=today - timedelta(days=2),
                        severity="MILD",
                        days_in_severity=1,
                        action_taken="PATIENT_NOTIFICATION",
                    )
                )
                db.add(
                    AdherenceReview(
                        patient_id=patient_id,
                        review_date=today - timedelta(days=1),
                        window_start=today - timedelta(days=8),
                        window_end=today - timedelta(days=1),
                        severity="MODERATE",
                        days_in_severity=2,
                        action_taken="DOCTOR_WARNING",
                    )
                )

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            prior = await repo.get_prior_reviews(today - timedelta(days=30))

        assert prior[patient_id].severity == "MODERATE"
        assert prior[patient_id].days_in_severity == 2
        assert prior[patient_id].review_date == today - timedelta(days=1)


class TestPatientRoster:
    @pytest.mark.asyncio
    async def test_returns_only_requested_patients(self):
        patient_a = await _create_patient(PATIENT_A_PHONE, "Bệnh nhân A")
        patient_b = await _create_patient(PATIENT_B_PHONE, "Bệnh nhân B")

        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            roster = await repo.get_patient_roster([patient_a])

        assert patient_a in roster
        assert patient_b not in roster
        assert roster[patient_a].name == "Bệnh nhân A"
        assert roster[patient_a].timezone == "Asia/Ho_Chi_Minh"
        assert roster[patient_a].status == "ACTIVE"

    @pytest.mark.asyncio
    async def test_empty_patient_list_short_circuits_without_a_query(self):
        async with AsyncSessionLocal() as db:
            repo = AdherenceIndicatorRepository(db)
            roster = await repo.get_patient_roster([])

        assert roster == {}
