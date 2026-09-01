"""Slice 5: prescriptions and their line items.

The Human-in-the-Loop rule lives here: only the prescribing doctor may write,
and an APPROVED prescription is frozen. These tests pin both, plus the
find-or-create-patient-by-phone flow that POST /prescriptions runs.
"""
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, select

from src.core.database import AsyncSessionLocal, engine
from src.core.security import hash_password
from src.modules.admin.models import DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import CaregiverLink, PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Medication, Prescription, PrescriptionItem

DOCTOR_PHONE = "+84900800001"
OTHER_DOCTOR_PHONE = "+84900800002"
PATIENT_PHONE = "+84900800010"
OTHER_PATIENT_PHONE = "+84900800012"
NEW_PATIENT_PHONE = "+84900800011"
CAREGIVER_PHONE = "+84900800013"
INACTIVE_CAREGIVER_PHONE = "+84900800014"
PIN = "123456"
MED_SOURCE_KEY = "TEST-SLICE5-MED"

_TEST_PHONES = [
    DOCTOR_PHONE,
    OTHER_DOCTOR_PHONE,
    PATIENT_PHONE,
    OTHER_PATIENT_PHONE,
    NEW_PATIENT_PHONE,
    CAREGIVER_PHONE,
    INACTIVE_CAREGIVER_PHONE,
]


async def _purge() -> None:
    """Clear everything hanging off this module's fixed phone numbers.

    Runs on both sides of every test rather than in a finally block: a test
    that dies while building fixtures never reaches its own cleanup, and the
    leftover User rows then collide with users_phone_key on the next run,
    turning one failure into a permanently red file.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (
                (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES))))
                .scalars()
                .all()
            )
            if ids:
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
                    item_ids = (
                        (
                            await db.execute(
                                select(PrescriptionItem.id).where(
                                    PrescriptionItem.prescription_id.in_(rx_ids)
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if item_ids:
                        await db.execute(
                            delete(ScheduledDose).where(
                                ScheduledDose.prescription_item_id.in_(item_ids)
                            )
                        )
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
    """Fresh pool, then a clean slate, on both sides of every test.

    The dispose has to come first: pytest-asyncio gives each test its own event
    loop, and a pooled asyncpg connection opened under the previous one raises
    "another operation is in progress" as soon as the purge query touches it.
    """
    await engine.dispose()
    await _purge()
    yield
    await _purge()
    await engine.dispose()


async def _create_doctor(phone: str, name: str, license_no: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="DOCTOR"
            )
            await DoctorRepository(db).create_doctor_profile(
                user_id=user.id, name=name, license_no=license_no
            )
        return user.id


async def _create_patient(phone: str, name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="PATIENT"
            )
            # Through the repository: timezone is NOT NULL with no server
            # default, and the repository is where its value is decided.
            await PatientRepository(db).create_patient_profile(user_id=user.id, name=name)
        return user.id


async def _create_caregiver(phone: str, patient_id: uuid.UUID, status: str = "ACTIVE") -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="CAREGIVER"
            )
            db.add(CaregiverLink(
                patient_id=patient_id, caregiver_user_id=user.id,
                status=status, channels=["APP_NOTIFICATION"],
            ))
        return user.id


async def _create_medication(name: str = "Amlodipin 5mg") -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            med = Medication(
                name=name,
                composition="Amlodipine besylate 5mg",
                uses="Hạ huyết áp",
                source_name="TEST",
                source_record_key=MED_SOURCE_KEY,
                is_active=True,
            )
            db.add(med)
            await db.flush()
            return med.id


async def _login(client, phone: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": PIN}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _item_payload(medication_id: uuid.UUID, **overrides) -> dict:
    payload = {
        "medication_id": str(medication_id),
        "dose_unit": "VIEN",
        "morning_dose": 1,
        "evening_dose": 1,
        "route": "ORAL",
        "meal_relation": "AFTER_MEAL",
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
    }
    payload.update(overrides)
    return payload


def _rx_payload(phone: str, **overrides) -> dict:
    payload = {
        "phone": phone,
        "name": "Nguyễn Văn A",
        "dob": "1985-05-15",
        "sex": "MALE",
        "emergency_note": "Tiền sử dị ứng penicillin",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# POST /prescriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_authentication(client):
    response = await client.post(
        "/api/v1/prescriptions", json=_rx_payload(PATIENT_PHONE)
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_rejects_patient_role(client):
    """HITL: only a doctor may write a prescription."""
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, PATIENT_PHONE)
    response = await client.post(
        "/api/v1/prescriptions", json=_rx_payload(PATIENT_PHONE), headers=headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_starts_as_draft_for_existing_patient(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(
            PATIENT_PHONE,
            diagnosis_note="I10 - Tăng huyết áp",
            items=[_item_payload(med_id)],
        ),
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    rx = data["prescription"]
    assert rx["status"] == "DRAFT"
    assert rx["patient_id"] == str(patient_id)
    assert rx["approved_at"] is None
    assert len(rx["items"]) == 1
    # display_name is snapshotted server-side from the catalog, never client input.
    assert rx["items"][0]["display_name"] == "Amlodipin 5mg"
    # The patient already existed, so no account was provisioned.
    assert data["temp_password"] is None


@pytest.mark.asyncio
async def test_create_provisions_account_for_unknown_phone(client):
    """Find-or-create: an unknown phone gets a PATIENT account in the same
    transaction, and the one-time PIN comes back exactly once."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(NEW_PATIENT_PHONE, items=[_item_payload(med_id)]),
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert len(data["temp_password"]) == 6
    assert data["temp_password"].isdigit()

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.phone == NEW_PATIENT_PHONE))
        ).scalar_one()
        assert user.role == "PATIENT"
        assert str(user.id) == data["prescription"]["patient_id"]


@pytest.mark.asyncio
async def test_create_provisions_account_with_demographics(client):
    """Verifies that patient_profiles record is created with the exact demographics
    passed in POST /prescriptions when the phone is not previously registered."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(
            NEW_PATIENT_PHONE,
            name="Trần Thị B",
            dob="1978-11-20",
            sex="FEMALE",
            emergency_note="Liên hệ con trai 0901234567",
            items=[_item_payload(med_id)],
        ),
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    patient_id = uuid.UUID(data["prescription"]["patient_id"])

    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(PatientProfile).where(PatientProfile.user_id == patient_id)
            )
        ).scalar_one()
        assert profile.name == "Trần Thị B"
        assert profile.dob == date(1978, 11, 20)
        assert profile.sex == "FEMALE"
        assert profile.emergency_note == "Liên hệ con trai 0901234567"


@pytest.mark.asyncio
async def test_create_rejects_invalid_dob(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    headers = await _login(client, DOCTOR_PHONE)

    # Future date of birth
    future_dob = (date.today() + timedelta(days=1)).isoformat()
    resp_future = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(NEW_PATIENT_PHONE, dob=future_dob),
        headers=headers,
    )
    assert resp_future.status_code == 422

    # Year <= 1900
    resp_old = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(NEW_PATIENT_PHONE, dob="1899-12-31"),
        headers=headers,
    )
    assert resp_old.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_invalid_sex(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(NEW_PATIENT_PHONE, sex="UNKNOWN_GENDER"),
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_unknown_medication(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(PATIENT_PHONE, items=[_item_payload(uuid.uuid4())]),
        headers=headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Approval and the frozen-after-approval rule
# ---------------------------------------------------------------------------


async def _draft_with_item(client, headers, med_id) -> dict:
    response = await client.post(
        "/api/v1/prescriptions",
        json=_rx_payload(PATIENT_PHONE, items=[_item_payload(med_id)]),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["data"]["prescription"]


@pytest.mark.asyncio
async def test_approve_stamps_time_and_freezes_the_prescription(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    approved = await client.post(
        f"/api/v1/prescriptions/{draft['id']}/approve", headers=headers
    )
    assert approved.status_code == 200
    body = approved.json()["data"]
    assert body["status"] == "APPROVED"
    assert body["approved_at"] is not None

    # Items are locked once approved — the whole point of the HITL boundary.
    add_item = await client.post(
        f"/api/v1/prescriptions/{draft['id']}/items",
        json=_item_payload(med_id),
        headers=headers,
    )
    assert add_item.status_code == 422

    delete_item = await client.delete(
        f"/api/v1/prescriptions/{draft['id']}/items/{draft['items'][0]['id']}",
        headers=headers,
    )
    assert delete_item.status_code == 422


@pytest.mark.asyncio
async def test_approving_twice_is_rejected(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    first = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve", headers=headers)
    assert second.status_code in (409, 422)


@pytest.mark.asyncio
async def test_another_doctor_cannot_approve_or_edit(client):
    """A doctor's write access is scoped to prescriptions they wrote."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_doctor(OTHER_DOCTOR_PHONE, "Dr Rx B", "LIC-RX-B")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()

    owner_headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, owner_headers, med_id)

    intruder_headers = await _login(client, OTHER_DOCTOR_PHONE)
    approve = await client.post(
        f"/api/v1/prescriptions/{draft['id']}/approve", headers=intruder_headers
    )
    assert approve.status_code in (403, 404)

    update = await client.put(
        f"/api/v1/prescriptions/{draft['id']}",
        json={"diagnosis_note": "hijacked"},
        headers=intruder_headers,
    )
    assert update.status_code in (403, 404)


@pytest.mark.asyncio
async def test_cancel_clears_future_pending_doses(client):
    """A cancelled prescription must not leave doses behind for the
    missed-dose scan to flag as MISSED later."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve", headers=headers)

    from datetime import datetime, timezone

    future = datetime.now(timezone.utc) + timedelta(days=1)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(
                ScheduledDose(
                    prescription_item_id=uuid.UUID(draft["items"][0]["id"]),
                    patient_id=patient_id,
                    original_scheduled_at=future,
                    current_scheduled_at=future,
                    status="PENDING",
                )
            )

    cancelled = await client.post(
        f"/api/v1/prescriptions/{draft['id']}/cancel",
        json={"cancel_reason": "Đổi phác đồ"},
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    async with AsyncSessionLocal() as db:
        remaining = (
            await db.execute(
                select(ScheduledDose).where(ScheduledDose.patient_id == patient_id)
            )
        ).scalars().all()
    assert remaining == []


# ---------------------------------------------------------------------------
# Reading prescriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_can_read_own_prescriptions(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    await _draft_with_item(client, doctor_headers, med_id)

    patient_headers = await _login(client, PATIENT_PHONE)
    response = await client.get(
        f"/api/v1/patients/{patient_id}/prescriptions", headers=patient_headers
    )
    assert response.status_code == 200
    page = response.json()["data"]
    assert page["total_elements"] == 1
    assert page["content"][0]["patient_id"] == str(patient_id)


@pytest.mark.asyncio
async def test_current_medications_returns_only_approved_date_active_items(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)

    active = await _draft_with_item(client, doctor_headers, med_id)
    await client.post(f"/api/v1/prescriptions/{active['id']}/approve", headers=doctor_headers)

    # A draft item must never be presented as a medicine the patient is using.
    await _draft_with_item(client, doctor_headers, med_id)

    expired_response = await client.post(
        "/api/v1/prescriptions",
        json={
            "phone": PATIENT_PHONE,
            "name": "Bệnh nhân A",
            "dob": "1980-01-01",
            "sex": "FEMALE",
            "items": [
                _item_payload(
                    med_id,
                    start_date=(date.today() - timedelta(days=10)).isoformat(),
                    end_date=(date.today() - timedelta(days=1)).isoformat(),
                )
            ],
        },
        headers=doctor_headers,
    )
    expired = expired_response.json()["data"]["prescription"]
    await client.post(f"/api/v1/prescriptions/{expired['id']}/approve", headers=doctor_headers)

    patient_headers = await _login(client, PATIENT_PHONE)
    response = await client.get(
        "/api/v1/patients/me/medications/current", headers=patient_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["as_of"] == date.today().isoformat()
    assert [item["id"] for item in data["medications"]] == [active["items"][0]["id"]]


@pytest.mark.asyncio
async def test_current_medications_requires_patient_authentication(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    doctor_headers = await _login(client, DOCTOR_PHONE)

    unauthenticated = await client.get("/api/v1/patients/me/medications/current")
    wrong_role = await client.get(
        "/api/v1/patients/me/medications/current", headers=doctor_headers
    )

    assert unauthenticated.status_code == 401
    assert wrong_role.status_code == 403


@pytest.mark.asyncio
async def test_patient_cannot_read_another_patients_prescriptions(client):
    """Out-of-scope reads come back as an empty page, not 403/404 — the same
    list-style filtering the dashboard roster uses, which avoids confirming
    which patient ids exist. What matters is that no row leaks."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    await _draft_with_item(client, doctor_headers, med_id)

    victim_id = await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    intruder_headers = await _login(client, PATIENT_PHONE)

    response = await client.get(
        f"/api/v1/patients/{victim_id}/prescriptions", headers=intruder_headers
    )
    assert response.status_code == 200
    page = response.json()["data"]
    assert page["content"] == []
    assert page["total_elements"] == 0


@pytest.mark.asyncio
async def test_patient_cannot_read_another_patients_prescription_by_id(client):
    """The detail route is the one that could leak a specific record."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    victims_rx = await _draft_with_item(client, doctor_headers, med_id)

    await _create_patient(OTHER_PATIENT_PHONE, "Bệnh nhân B")
    intruder_headers = await _login(client, OTHER_PATIENT_PHONE)

    response = await client.get(
        f"/api/v1/prescriptions/{victims_rx['id']}", headers=intruder_headers
    )
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_unknown_prescription_returns_404(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    headers = await _login(client, DOCTOR_PHONE)
    response = await client.get(f"/api/v1/prescriptions/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_item_to_draft_succeeds(client):
    """POST /prescriptions/{id}/items is the documented way to build a DRAFT
    up incrementally, so it must work on a DRAFT prescription."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)

    created = await client.post(
        "/api/v1/prescriptions", json=_rx_payload(PATIENT_PHONE), headers=headers
    )
    assert created.status_code == 201
    rx_id = created.json()["data"]["prescription"]["id"]

    response = await client.post(
        f"/api/v1/prescriptions/{rx_id}/items",
        json=_item_payload(med_id),
        headers=headers,
    )
    assert response.status_code == 201
    item = response.json()["data"]
    assert item["display_name"] == "Amlodipin 5mg"
    assert item["prescription_id"] == rx_id


@pytest.mark.asyncio
async def test_update_item_on_draft_resnapshots_display_name(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    response = await client.put(
        f"/api/v1/prescriptions/{draft['id']}/items/{draft['items'][0]['id']}",
        json=_item_payload(med_id, morning_dose=2),
        headers=headers,
    )
    assert response.status_code == 200
    assert float(response.json()["data"]["morning_dose"]) == 2.0


@pytest.mark.asyncio
async def test_delete_item_from_draft(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    response = await client.delete(
        f"/api/v1/prescriptions/{draft['id']}/items/{draft['items'][0]['id']}",
        headers=headers,
    )
    assert response.status_code == 200

    detail = await client.get(f"/api/v1/prescriptions/{draft['id']}", headers=headers)
    assert detail.json()["data"]["items"] == []


# ---------------------------------------------------------------------------
# GET /doctors/patients/by-phone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_patient_by_phone_succeeds(client):
    """Doctor can fetch patient details by phone globally even before writing a prescription."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.get(
        "/api/v1/doctors/patients/by-phone",
        params={"phone": PATIENT_PHONE},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["phone"] == PATIENT_PHONE
    assert data["name"] == "Bệnh nhân A"
    assert data["user_id"] == str(patient_id)


@pytest.mark.asyncio
async def test_get_patient_by_phone_not_found(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.get(
        "/api/v1/doctors/patients/by-phone",
        params={"phone": NEW_PATIENT_PHONE},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_patient_by_phone_forbidden_for_patient(client):
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, PATIENT_PHONE)

    response = await client.get(
        "/api/v1/doctors/patients/by-phone",
        params={"phone": PATIENT_PHONE},
        headers=headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /prescriptions/{id}/pdf
#
# Access mirrors GET /prescriptions/{id} exactly (self / doctor-prescribed /
# active-caregiver, out-of-scope -> 404) — these tests pin that it stays that
# way rather than drifting into a parallel rule. See
# docs/prescription-pdf-export-plan.md for the full design.
# ---------------------------------------------------------------------------


async def _approved_with_item(client, headers, med_id) -> dict:
    draft = await _draft_with_item(client, headers, med_id)
    approved = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve", headers=headers)
    assert approved.status_code == 200
    return approved.json()["data"]


@pytest.mark.asyncio
async def test_export_pdf_requires_approved_draft_rejected(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    response = await client.get(f"/api/v1/prescriptions/{draft['id']}/pdf", headers=headers)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_export_pdf_rejects_cancelled(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    draft = await _draft_with_item(client, headers, med_id)

    cancelled = await client.post(
        f"/api/v1/prescriptions/{draft['id']}/cancel",
        json={"cancel_reason": "Đổi phác đồ"},
        headers=headers,
    )
    assert cancelled.status_code == 200

    response = await client.get(f"/api/v1/prescriptions/{draft['id']}/pdf", headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_pdf_returns_document_for_owning_doctor(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, headers, med_id)

    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert response.headers["cache-control"] == "no-store"
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert approved["id"][:8] in disposition


@pytest.mark.asyncio
async def test_export_pdf_returns_document_for_patient_self(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, doctor_headers, med_id)

    patient_headers = await _login(client, PATIENT_PHONE)
    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=patient_headers)
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_export_pdf_returns_document_for_active_caregiver(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_caregiver(CAREGIVER_PHONE, patient_id, status="ACTIVE")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, doctor_headers, med_id)

    caregiver_headers = await _login(client, CAREGIVER_PHONE)
    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=caregiver_headers)
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_export_pdf_hides_from_inactive_caregiver(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_caregiver(INACTIVE_CAREGIVER_PHONE, patient_id, status="INACTIVE")
    med_id = await _create_medication()
    doctor_headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, doctor_headers, med_id)

    caregiver_headers = await _login(client, INACTIVE_CAREGIVER_PHONE)
    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=caregiver_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_pdf_hides_from_other_doctor(client):
    """404, not 403 — indistinguishable from a prescription that doesn't exist."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_doctor(OTHER_DOCTOR_PHONE, "Dr Rx B", "LIC-RX-B")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    owner_headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, owner_headers, med_id)

    other_headers = await _login(client, OTHER_DOCTOR_PHONE)
    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=other_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_pdf_nonexistent_id_returns_404(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    headers = await _login(client, DOCTOR_PHONE)

    response = await client.get(f"/api/v1/prescriptions/{uuid.uuid4()}/pdf", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_pdf_unauthenticated_returns_401(client):
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, headers, med_id)

    response = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_export_pdf_repeat_download_is_not_blocked(client):
    """No hard one-shot limit at the backend — GET stays idempotent. The
    portal's 'shown once' button is a frontend affordance only; see
    docs/prescription-pdf-export-plan.md §3."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)
    approved = await _approved_with_item(client, headers, med_id)

    first = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=headers)
    second = await client.get(f"/api/v1/prescriptions/{approved['id']}/pdf", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_export_pdf_query_count_is_constant_regardless_of_item_count(client):
    """Guards against a regression back to per-item medication lookups
    (MedicationRepository.list_by_ids exists specifically to avoid this)."""
    await _create_doctor(DOCTOR_PHONE, "Dr Rx A", "LIC-RX-A")
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    med_id = await _create_medication()
    headers = await _login(client, DOCTOR_PHONE)

    async def _approved_with_n_items(n: int) -> str:
        create = await client.post(
            "/api/v1/prescriptions",
            json=_rx_payload(PATIENT_PHONE, items=[_item_payload(med_id) for _ in range(n)]),
            headers=headers,
        )
        assert create.status_code == 201
        rx_id = create.json()["data"]["prescription"]["id"]
        approve = await client.post(f"/api/v1/prescriptions/{rx_id}/approve", headers=headers)
        assert approve.status_code == 200
        return rx_id

    async def _export_query_count(rx_id: str) -> int:
        statements: list[str] = []

        def _log(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _log)
        try:
            response = await client.get(f"/api/v1/prescriptions/{rx_id}/pdf", headers=headers)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _log)
        assert response.status_code == 200
        return len(statements)

    rx_2 = await _approved_with_n_items(2)
    rx_20 = await _approved_with_n_items(20)
    count_2 = await _export_query_count(rx_2)
    count_20 = await _export_query_count(rx_20)

    assert count_2 == count_20, f"N+1 regression: {count_2} queries for 2 items vs {count_20} for 20"

