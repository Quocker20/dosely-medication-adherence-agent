"""Slice 7: adherence logging, health surveys, and safety alerts.

The safety-critical parts pinned here are idempotency (a retried tap must not
page a doctor twice, nor double-count a dose) and the alert lifecycle a doctor
drives from the portal.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.adherence.models import AdherenceLog, Alert, HealthSurvey, SymptomReport
from src.modules.admin.models import AuditLog, DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Medication, Prescription, PrescriptionItem

DOCTOR_PHONE = "+84900900001"
PATIENT_PHONE = "+84900900010"
OTHER_PATIENT_PHONE = "+84900900011"
PIN = "123456"
MED_SOURCE_KEY = "TEST-SLICE7-MED"

_TEST_PHONES = [DOCTOR_PHONE, PATIENT_PHONE, OTHER_PATIENT_PHONE]


async def _purge() -> None:
    """Clear everything hanging off this module's fixed phone numbers.

    Runs on both sides of every test rather than in a finally block: a test
    that dies mid-fixture never reaches its own cleanup, and the leftover User
    rows then collide with users_phone_key on the next run.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (
                (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES))))
                .scalars()
                .all()
            )
            if ids:
                await db.execute(delete(AdherenceLog).where(AdherenceLog.patient_id.in_(ids)))
                await db.execute(delete(SymptomReport).where(SymptomReport.patient_id.in_(ids)))
                await db.execute(delete(HealthSurvey).where(HealthSurvey.patient_id.in_(ids)))
                await db.execute(delete(Alert).where(Alert.patient_id.in_(ids)))
                await db.execute(delete(AuditLog).where(AuditLog.actor_user_id.in_(ids)))
                await db.execute(delete(ScheduledDose).where(ScheduledDose.patient_id.in_(ids)))
                rx_ids = (
                    (
                        await db.execute(
                            select(Prescription.id).where(
                                Prescription.patient_id.in_(ids)
                                | Prescription.doctor_id.in_(ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if rx_ids:
                    await db.execute(
                        delete(PrescriptionItem).where(
                            PrescriptionItem.prescription_id.in_(rx_ids)
                        )
                    )
                    await db.execute(delete(Prescription).where(Prescription.id.in_(rx_ids)))
                await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
                await db.execute(delete(DoctorProfile).where(DoctorProfile.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
            await db.execute(
                delete(Medication).where(Medication.source_record_key == MED_SOURCE_KEY)
            )


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    """Fresh pool, then a clean slate, on both sides of every test — see the
    matching fixture in test_prescriptions.py for why dispose comes first."""
    await engine.dispose()
    await _purge()
    yield
    await _purge()
    await engine.dispose()


async def _create_doctor() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=DOCTOR_PHONE, hashed_password=hash_password(PIN), role="DOCTOR"
            )
            await DoctorRepository(db).create_doctor_profile(
                user_id=user.id, name="Dr Slice7", license_no="LIC-SLICE7"
            )
        return user.id


async def _create_patient(phone: str = PATIENT_PHONE, name: str = "Bệnh nhân A") -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="PATIENT"
            )
            await PatientRepository(db).create_patient_profile(user_id=user.id, name=name)
        return user.id


async def _create_dose(patient_id: uuid.UUID, doctor_id: uuid.UUID, when=None) -> uuid.UUID:
    """A scheduled dose reachable by the adherence endpoints, built through the
    real chain (prescription -> item -> dose) so FKs and scoping behave."""
    when = when or (datetime.now(timezone.utc) - timedelta(minutes=30))
    async with AsyncSessionLocal() as db:
        async with db.begin():
            med = Medication(
                name="Amlodipin 5mg",
                source_name="TEST",
                source_record_key=MED_SOURCE_KEY,
                is_active=True,
            )
            db.add(med)
            await db.flush()

            rx = Prescription(
                patient_id=patient_id, doctor_id=doctor_id, status="APPROVED"
            )
            db.add(rx)
            await db.flush()

            item = PrescriptionItem(
                prescription_id=rx.id,
                medication_id=med.id,
                display_name="Amlodipin 5mg",
                dose_unit="VIEN",
                morning_dose=1,
                start_date=date.today(),
            )
            db.add(item)
            await db.flush()

            dose = ScheduledDose(
                prescription_item_id=item.id,
                patient_id=patient_id,
                original_scheduled_at=when,
                current_scheduled_at=when,
                status="PENDING",
            )
            db.add(dose)
            await db.flush()
            return dose.id


async def _login(client, phone: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": PIN}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


# ---------------------------------------------------------------------------
# POST /scheduled-doses/{id}/actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dose_action_requires_authentication(client):
    response = await client.post(
        f"/api/v1/scheduled-doses/{uuid.uuid4()}/actions", json={"action": "TAKEN"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dose_action_records_and_flips_status(client):
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(patient_id, doctor_id)
    headers = {**await _login(client, PATIENT_PHONE), **_idem("dose-1-taken")}

    response = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )
    assert response.status_code == 201
    log = response.json()["data"]
    assert log["action"] == "TAKEN"
    assert log["patient_id"] == str(patient_id)
    assert log["scheduled_dose_id"] == str(dose_id)

    async with AsyncSessionLocal() as db:
        dose = (
            await db.execute(select(ScheduledDose).where(ScheduledDose.id == dose_id))
        ).scalar_one()
        assert dose.status == "TAKEN"


@pytest.mark.asyncio
async def test_dose_action_before_scheduled_time_is_rejected(client):
    """The server must reject early confirmations even if a client bypasses
    its disabled controls or has a clock that is ahead."""
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(
        patient_id,
        doctor_id,
        when=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    headers = {**await _login(client, PATIENT_PHONE), **_idem("dose-too-early-1")}

    response = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Scheduled dose is not due yet"

    async with AsyncSessionLocal() as db:
        dose = (
            await db.execute(select(ScheduledDose).where(ScheduledDose.id == dose_id))
        ).scalar_one()
        logs = (
            await db.execute(
                select(AdherenceLog).where(AdherenceLog.scheduled_dose_id == dose_id)
            )
        ).scalars().all()
    assert dose.status == "PENDING"
    assert logs == []


@pytest.mark.asyncio
async def test_dose_action_replays_on_repeated_idempotency_key(client):
    """A retried delivery must replay the original log, not add a second —
    double-counting intake would distort the adherence rate a doctor reads."""
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(patient_id, doctor_id)
    headers = {**await _login(client, PATIENT_PHONE), **_idem("dose-retry-1")}

    first = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert second.json()["data"]["id"] == first.json()["data"]["id"]

    async with AsyncSessionLocal() as db:
        logs = (
            (
                await db.execute(
                    select(AdherenceLog).where(AdherenceLog.patient_id == patient_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_dose_action_of_another_patient_is_rejected(client):
    doctor_id = await _create_doctor()
    victim_id = await _create_patient()
    dose_id = await _create_dose(victim_id, doctor_id)

    await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    headers = {**await _login(client, OTHER_PATIENT_PHONE), **_idem("intruder-1")}

    response = await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers=headers,
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# GET /patients/{id}/adherence and .../adherence/logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adherence_summary_counts_the_recorded_dose(client):
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(patient_id, doctor_id)
    headers = await _login(client, PATIENT_PHONE)
    await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers={**headers, **_idem("summary-1")},
    )

    today = date.today()
    response = await client.get(
        f"/api/v1/patients/{patient_id}/adherence",
        params={"from": today.isoformat(), "to": today.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200
    summary = response.json()["data"]
    assert summary["total_doses"] == 1
    assert summary["taken_doses"] == 1
    assert summary["adherence_rate"] == 100.0


@pytest.mark.asyncio
async def test_adherence_logs_are_paginated(client):
    doctor_id = await _create_doctor()
    patient_id = await _create_patient()
    dose_id = await _create_dose(patient_id, doctor_id)
    headers = await _login(client, PATIENT_PHONE)
    await client.post(
        f"/api/v1/scheduled-doses/{dose_id}/actions",
        json={"action": "TAKEN"},
        headers={**headers, **_idem("logs-1")},
    )

    today = date.today()
    response = await client.get(
        f"/api/v1/patients/{patient_id}/adherence/logs",
        params={"from": today.isoformat(), "to": today.isoformat(), "page": 1, "size": 10},
        headers=headers,
    )
    assert response.status_code == 200
    page = response.json()["data"]
    assert page["total_elements"] == 1
    assert page["content"][0]["action"] == "TAKEN"


# ---------------------------------------------------------------------------
# POST /patients/{id}/health-surveys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_survey_submits(client):
    patient_id = await _create_patient()
    headers = await _login(client, PATIENT_PHONE)

    response = await client.post(
        f"/api/v1/patients/{patient_id}/health-surveys",
        json={
            "survey_date": date.today().isoformat(),
            "answers_json": {"huyet_ap": "130/85"},
            "symptoms": [
                {"symptom_code": "DIZZY", "severity": "MILD", "description": "hơi chóng mặt"}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["status"] == "SUBMITTED"


@pytest.mark.asyncio
async def test_severe_symptom_in_survey_raises_an_alert(client):
    """A SEVERE symptom is one of the Red Alert triggers — it must reach the
    doctor's queue without the patient having to press SOS."""
    await _create_doctor()
    patient_id = await _create_patient()
    patient_headers = await _login(client, PATIENT_PHONE)

    await client.post(
        f"/api/v1/patients/{patient_id}/health-surveys",
        json={
            "survey_date": date.today().isoformat(),
            "answers_json": {},
            "symptoms": [
                {"symptom_code": "CHEST_PAIN", "severity": "SEVERE", "description": "tức ngực"}
            ],
        },
        headers=patient_headers,
    )

    doctor_headers = await _login(client, DOCTOR_PHONE)
    alerts = await client.get(
        "/api/v1/alerts", params={"patientId": str(patient_id)}, headers=doctor_headers
    )
    assert alerts.status_code == 200
    content = alerts.json()["data"]["content"]
    assert len(content) == 1
    assert content[0]["triggered_by_type"] == "SEVERE_SYMPTOM"


@pytest.mark.asyncio
async def test_survey_for_another_patient_is_rejected(client):
    victim_id = await _create_patient()
    await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    headers = await _login(client, OTHER_PATIENT_PHONE)

    response = await client.post(
        f"/api/v1/patients/{victim_id}/health-surveys",
        json={"survey_date": date.today().isoformat(), "answers_json": {}, "symptoms": []},
        headers=headers,
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# POST /patients/{id}/sos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sos_defaults_to_a_critical_button_press(client):
    patient_id = await _create_patient()
    headers = {**await _login(client, PATIENT_PHONE), **_idem("sos-1")}

    response = await client.post(
        f"/api/v1/patients/{patient_id}/sos",
        json={"message": "Tôi thấy rất mệt"},
        headers=headers,
    )
    assert response.status_code == 201
    alert = response.json()["data"]
    assert alert["status"] == "OPEN"
    assert alert["triggered_by_type"] == "SOS_BUTTON"
    assert alert["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_sos_records_an_agent_detected_source(client):
    """The agent shares this route; triggered_by_type/severity are what let a
    doctor tell a detection from a button press."""
    patient_id = await _create_patient()
    headers = {**await _login(client, PATIENT_PHONE), **_idem("sos-agent-1")}

    response = await client.post(
        f"/api/v1/patients/{patient_id}/sos",
        json={
            "message": "[HIGH] SEVERE_SYMPTOM: tức ngực",
            "triggered_by_type": "SEVERE_SYMPTOM",
            "severity": "HIGH",
        },
        headers=headers,
    )
    assert response.status_code == 201
    alert = response.json()["data"]
    assert alert["triggered_by_type"] == "SEVERE_SYMPTOM"
    assert alert["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_sos_replays_on_repeated_idempotency_key(client):
    """A double-tap must not page a doctor with two CRITICAL alerts."""
    patient_id = await _create_patient()
    headers = {**await _login(client, PATIENT_PHONE), **_idem("sos-retry-1")}

    first = await client.post(
        f"/api/v1/patients/{patient_id}/sos", json={"message": "cứu"}, headers=headers
    )
    second = await client.post(
        f"/api/v1/patients/{patient_id}/sos", json={"message": "cứu"}, headers=headers
    )
    assert first.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]

    async with AsyncSessionLocal() as db:
        alerts = (
            (await db.execute(select(Alert).where(Alert.patient_id == patient_id)))
            .scalars()
            .all()
        )
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_sos_for_another_patient_is_rejected(client):
    victim_id = await _create_patient()
    await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    headers = {**await _login(client, OTHER_PATIENT_PHONE), **_idem("sos-intruder")}

    response = await client.post(
        f"/api/v1/patients/{victim_id}/sos", json={"message": "x"}, headers=headers
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# GET /alerts, acknowledge, resolve
# ---------------------------------------------------------------------------


async def _raise_alert(client, patient_id: uuid.UUID, key: str) -> str:
    headers = {**await _login(client, PATIENT_PHONE), **_idem(key)}
    response = await client.post(
        f"/api/v1/patients/{patient_id}/sos", json={"message": "cứu"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_alerts_list_is_doctor_only(client):
    await _create_patient()
    headers = await _login(client, PATIENT_PHONE)
    response = await client.get("/api/v1/alerts", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_alert_lifecycle_open_acknowledge_resolve(client):
    await _create_doctor()
    patient_id = await _create_patient()
    alert_id = await _raise_alert(client, patient_id, "lifecycle-1")
    doctor_headers = await _login(client, DOCTOR_PHONE)

    ack = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=doctor_headers)
    assert ack.status_code == 200
    assert ack.json()["data"]["status"] == "ACKNOWLEDGED"

    resolved = await client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={"resolution_note": "Đã gọi điện, bệnh nhân ổn"},
        headers=doctor_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_acknowledging_twice_is_rejected(client):
    await _create_doctor()
    patient_id = await _create_patient()
    alert_id = await _raise_alert(client, patient_id, "ack-twice-1")
    doctor_headers = await _login(client, DOCTOR_PHONE)

    first = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=doctor_headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=doctor_headers)
    assert second.status_code in (409, 422)


@pytest.mark.asyncio
async def test_resolving_twice_is_rejected(client):
    await _create_doctor()
    patient_id = await _create_patient()
    alert_id = await _raise_alert(client, patient_id, "resolve-twice-1")
    doctor_headers = await _login(client, DOCTOR_PHONE)
    body = {"resolution_note": "xong"}

    first = await client.post(
        f"/api/v1/alerts/{alert_id}/resolve", json=body, headers=doctor_headers
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/alerts/{alert_id}/resolve", json=body, headers=doctor_headers
    )
    assert second.status_code in (409, 422)


@pytest.mark.asyncio
async def test_alerts_can_be_filtered_by_status(client):
    await _create_doctor()
    patient_id = await _create_patient()
    alert_id = await _raise_alert(client, patient_id, "filter-1")
    doctor_headers = await _login(client, DOCTOR_PHONE)

    open_page = await client.get(
        "/api/v1/alerts",
        params={"status": "OPEN", "patientId": str(patient_id)},
        headers=doctor_headers,
    )
    assert open_page.json()["data"]["total_elements"] == 1

    await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=doctor_headers)

    still_open = await client.get(
        "/api/v1/alerts",
        params={"status": "OPEN", "patientId": str(patient_id)},
        headers=doctor_headers,
    )
    assert still_open.json()["data"]["total_elements"] == 0

    acknowledged = await client.get(
        "/api/v1/alerts",
        params={"status": "ACKNOWLEDGED", "patientId": str(patient_id)},
        headers=doctor_headers,
    )
    assert acknowledged.json()["data"]["total_elements"] == 1


@pytest.mark.asyncio
async def test_unknown_alert_returns_404(client):
    await _create_doctor()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    response = await client.post(
        f"/api/v1/alerts/{uuid.uuid4()}/acknowledge", headers=doctor_headers
    )
    assert response.status_code == 404
