"""P-06 characterization: roster ordering / filters / pagination / counts.

Pins the exact output of DashboardRepository.list_dashboard_patients so the
correlated-subquery -> pre-aggregated-join refactor provably changes nothing.
"""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.modules.adherence.models import Alert, HealthSurvey
from src.modules.admin.models import DoctorProfile
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.dashboard.repository import DashboardRepository
from src.modules.patients.models import PatientProfile
from src.modules.prescriptions.models import Prescription, PrescriptionItem
from tests.test_api.test_dashboard import (
    _add_alert,
    _add_doses,
    _add_survey,
    _create_doctor,
    _create_patient,
    _create_prescription,
)

DOC = "+84900710001"
OTHER_DOC = "+84900710002"
PH = {k: f"+8490071002{i}" for i, k in enumerate("ABCDEX")}
_PHONES = [DOC, OTHER_DOC, *PH.values()]
OVERDUE = 30


async def _purge():
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(_PHONES)))).scalars().all()
            if not ids:
                return
            await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
            await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
            await db.execute(delete(HealthSurvey).where(HealthSurvey.patient_id.in_(ids)))
            await db.execute(delete(Prescription).where(Prescription.patient_id.in_(ids)))
            await db.execute(delete(Prescription).where(Prescription.doctor_id.in_(ids)))
            await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
            await db.execute(delete(DoctorProfile).where(DoctorProfile.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    await engine.dispose()
    await _purge()
    yield
    await _purge()
    await engine.dispose()


async def _dose_at(patient_id, rx_id, status, at):
    async with AsyncSessionLocal() as db:
        async with db.begin():
            item = PrescriptionItem(
                prescription_id=rx_id, display_name="X", dose_unit="VIEN",
                start_date=datetime.now(UTC).date(),
            )
            db.add(item)
            await db.flush()
            db.add(ScheduledDose(
                prescription_item_id=item.id, patient_id=patient_id,
                original_scheduled_at=at, current_scheduled_at=at, status=status,
                taken_at=at if status == "TAKEN" else None,
            ))


@pytest_asyncio.fixture
async def seeded():
    doc = await _create_doctor(DOC, "Dr Char", "LIC-CHAR-1")
    other = await _create_doctor(OTHER_DOC, "Dr Other", "LIC-CHAR-2")
    ids = {}
    for key, name in [("A", "An Alpha"), ("B", "Binh Beta"), ("C", "Chi Gamma"),
                      ("D", "Dung Delta"), ("E", "Em Epsilon")]:
        ids[key] = await _create_patient(PH[key], name)
    rx = {k: await _create_prescription(v, doc) for k, v in ids.items()}
    outsider = await _create_patient(PH["X"], "Xa Outsider")
    await _create_prescription(outsider, other)
    now = datetime.now(UTC)

    await _add_doses(ids["A"], rx["A"], ["TAKEN", "MISSED", "MISSED", "MISSED"])
    await _dose_at(ids["A"], rx["A"], "TAKEN", now - timedelta(days=20))  # outside window
    await _add_doses(ids["B"], rx["B"], ["TAKEN", "TAKEN", "MISSED", "MISSED"])
    await _add_doses(ids["C"], rx["C"], ["TAKEN"] * 7 + ["MISSED"] * 3)
    await _dose_at(ids["C"], rx["C"], "PENDING", now + timedelta(hours=2))  # future
    await _dose_at(ids["C"], rx["C"], "PENDING", now - timedelta(minutes=5))  # in grace
    await _dose_at(ids["C"], rx["C"], "PENDING", now - timedelta(hours=3))  # overdue -> due
    await _add_doses(ids["E"], rx["E"], ["TAKEN", "TAKEN", "TAKEN"])

    await _add_alert(ids["A"], severity="CRITICAL")
    await _add_alert(ids["A"], status="RESOLVED", severity="CRITICAL")
    for _ in range(2):
        await _add_alert(ids["B"], alert_type="WARNING", severity="MEDIUM")
    await _add_alert(ids["D"], status="ACKNOWLEDGED", severity="HIGH")
    await _add_alert(ids["D"], status="RESOLVED", severity="HIGH")
    await _add_alert(ids["E"], severity="CRITICAL")
    await _add_alert(ids["E"], alert_type="WARNING", severity="MEDIUM")
    await _add_survey(ids["E"], now.date() - timedelta(days=3))
    await _add_survey(ids["E"], now.date() - timedelta(days=1))
    await _add_survey(ids["A"], now.date() - timedelta(days=9))
    return doc, ids


async def _list(doc, **kw):
    async with AsyncSessionLocal() as db:
        return await DashboardRepository(db).list_dashboard_patients(
            range_start=datetime.now(UTC) - timedelta(days=7),
            overdue_minutes=OVERDUE, doctor_id=doc, **kw,
        )


def _names(rows):
    return [r[1] for r in rows]


@pytest.mark.asyncio
async def test_default_order_values_and_count(seeded):
    doc, ids = seeded
    rows, total = await _list(doc)
    assert total == 5
    # critical desc, warning desc, created_at desc
    assert _names(rows) == ["Em Epsilon", "Dung Delta", "An Alpha", "Binh Beta", "Chi Gamma"]
    by = {r[1]: r for r in rows}
    today = datetime.now(UTC).date()
    assert by["Em Epsilon"][2:] == (3, 3, 2, today - timedelta(days=1))
    assert by["Dung Delta"][2:] == (0, 0, 1, None)
    assert by["An Alpha"][2:] == (4, 1, 1, today - timedelta(days=9))
    assert by["Binh Beta"][2:] == (4, 2, 2, None)
    # 10 + overdue pending (due); future and in-grace pendings excluded
    assert by["Chi Gamma"][2:] == (11, 7, 0, None)


@pytest.mark.asyncio
async def test_adherence_band_filters(seeded):
    doc, _ = seeded
    assert _names((await _list(doc, adherence_band="LOW"))[0]) == ["An Alpha"]
    rows, total = await _list(doc, adherence_band="MEDIUM")
    # B = 50% (boundary, inclusive), C = 7/11 = 63.6%
    assert _names(rows) == ["Binh Beta", "Chi Gamma"] and total == 2
    rows, total = await _list(doc, adherence_band="HIGH")
    # zero-dose patient is in no band
    assert _names(rows) == ["Em Epsilon"] and total == 1


@pytest.mark.asyncio
async def test_search_and_alert_status(seeded):
    doc, _ = seeded
    assert _names((await _list(doc, search="delta"))[0]) == ["Dung Delta"]
    assert _names((await _list(doc, search=PH["B"][-4:]))[0]) == ["Binh Beta"]
    rows, total = await _list(doc, search="zzz")
    assert (rows, total) == ([], 0)
    rows, total = await _list(doc, alert_status="RESOLVED")
    assert set(_names(rows)) == {"An Alpha", "Dung Delta"} and total == 2
    rows, total = await _list(doc, alert_status="OPEN", adherence_band="LOW")
    assert _names(rows) == ["An Alpha"] and total == 1


@pytest.mark.asyncio
async def test_pagination(seeded):
    doc, _ = seeded
    full = _names((await _list(doc))[0])
    p1, t1 = await _list(doc, page=1, size=2)
    p2, t2 = await _list(doc, page=2, size=2)
    p3, t3 = await _list(doc, page=3, size=2)
    assert (t1, t2, t3) == (5, 5, 5)
    assert _names(p1) + _names(p2) + _names(p3) == full
    assert len(p3) == 1
    rows, total = await _list(doc, page=4, size=2)
    assert rows == [] and total == 5


@pytest.mark.asyncio
async def test_admin_unscoped_sees_all(seeded):
    rows, total = await _list(None, size=100)
    assert total == 6 and "Xa Outsider" in _names(rows)
