"""Slice 8 doctor portal: roster, patient panel, and the live event socket.

Access scoping is the point of most of these: a doctor's reach over a patient
is derived per request from having prescribed for them, so the roster and the
detail panel must both disappear the moment that fact does.
"""
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from starlette.websockets import WebSocketDisconnect

import src.core.redis as core_redis
from src.core.database import AsyncSessionLocal, engine
from src.core.redis import publish_dashboard_event
from src.core.security import create_access_token, create_refresh_token, hash_password
from src.main import app
from src.modules.adherence.models import Alert, HealthSurvey
from src.modules.admin.models import DoctorProfile
from src.modules.admin.repository import DoctorRepository
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.dashboard.service import DashboardEventService
from src.modules.patients.models import PatientProfile
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Prescription, PrescriptionItem

DOCTOR_PHONE = "+84900700001"
OTHER_DOCTOR_PHONE = "+84900700002"
ADMIN_PHONE = "+84900700003"
PATIENT_PHONE = "+84900700010"
PIN = "123456"


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


async def _create_admin(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="ADMIN"
            )
        return user.id


async def _create_patient(phone: str, name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await AuthRepository(db).create_user(
                phone=phone, hashed_password=hash_password(PIN), role="PATIENT"
            )
            # Through the repository rather than the model directly: timezone is
            # NOT NULL with no server default, and the repository is where its
            # value is decided.
            await PatientRepository(db).create_patient_profile(user_id=user.id, name=name)
        return user.id


async def _create_prescription(
    patient_id: uuid.UUID, doctor_id: uuid.UUID, status: str = "APPROVED"
) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            rx = Prescription(patient_id=patient_id, doctor_id=doctor_id, status=status)
            db.add(rx)
            await db.flush()
            return rx.id


async def _add_doses(patient_id: uuid.UUID, prescription_id: uuid.UUID, statuses: list[str]):
    """One prescription item plus a dose per requested status, all inside the
    dashboard's rolling window so they land in the adherence numerator."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            item = PrescriptionItem(
                prescription_id=prescription_id,
                display_name="Amlodipin 5mg",
                dose_unit="VIEN",
                start_date=datetime.now(timezone.utc).date(),
            )
            db.add(item)
            await db.flush()
            now = datetime.now(timezone.utc)
            for offset, status in enumerate(statuses):
                at = now - timedelta(hours=offset + 1)
                db.add(
                    ScheduledDose(
                        prescription_item_id=item.id,
                        patient_id=patient_id,
                        original_scheduled_at=at,
                        current_scheduled_at=at,
                        status=status,
                        taken_at=at if status == "TAKEN" else None,
                    )
                )


async def _add_alert(patient_id: uuid.UUID, status: str = "OPEN") -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            alert = Alert(
                patient_id=patient_id,
                triggered_by_type="SOS_BUTTON",
                alert_type="RED_ALERT",
                severity="CRITICAL",
                status=status,
                message="test alert",
                alert_metadata={},
            )
            db.add(alert)
            await db.flush()
            return alert.id


async def _add_survey(patient_id: uuid.UUID, day) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            db.add(
                HealthSurvey(
                    patient_id=patient_id,
                    survey_date=day,
                    status="SUBMITTED",
                    answers_json={},
                )
            )


_TEST_PHONES = [DOCTOR_PHONE, OTHER_DOCTOR_PHONE, ADMIN_PHONE, PATIENT_PHONE, "0900000019"]


async def _purge_test_users() -> None:
    """Delete everything hanging off this module's fixed phone numbers.

    Runs before and after every test rather than only in a finally block: a
    test that dies while building its fixtures never reaches its own cleanup,
    and the leftover User rows then collide with users_phone_key on the next
    run, turning one failure into a permanently red file.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (
                (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES))))
                .scalars()
                .all()
            )
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
async def _clean_slate():
    """Fresh pool, then a clean slate, on both sides of every test.

    The dispose has to come first, not just at teardown: pytest-asyncio gives
    each test its own event loop, and a pooled asyncpg connection opened under
    the previous one raises "another operation is in progress" the moment this
    fixture's own purge query touches it.
    """
    await engine.dispose()
    await _purge_test_users()
    yield
    await _purge_test_users()
    await engine.dispose()


async def _login(client, phone: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": PIN}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


# ---------------------------------------------------------------------------
# GET /dashboard/patients
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roster_requires_authentication(client):
    response = await client.get("/api/v1/dashboard/patients")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_roster_rejects_patient_role(client):
    await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, PATIENT_PHONE)
    response = await client.get("/api/v1/dashboard/patients", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_roster_shows_only_patients_this_doctor_prescribed_for(client):
    """A doctor holds no ownership over patients — the roster is derived from
    prescriptions written, so another doctor's patient must not appear."""
    await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    other_id = await _create_doctor(OTHER_DOCTOR_PHONE, "Dr Dash B", "LIC-DASH-B")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, other_id)

    headers = await _login(client, DOCTOR_PHONE)
    body = (await client.get("/api/v1/dashboard/patients", headers=headers)).json()
    assert body["success"] is True
    ids = [row["patient_id"] for row in body["data"]["content"]]
    assert str(patient_id) not in ids

    other_headers = await _login(client, OTHER_DOCTOR_PHONE)
    other_body = (
        await client.get("/api/v1/dashboard/patients", headers=other_headers)
    ).json()
    assert str(patient_id) in [r["patient_id"] for r in other_body["data"]["content"]]


@pytest.mark.asyncio
async def test_roster_row_carries_adherence_alerts_and_last_survey(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    rx_id = await _create_prescription(patient_id, doctor_id)
    await _add_doses(patient_id, rx_id, ["TAKEN", "TAKEN", "MISSED", "SKIPPED"])
    await _add_alert(patient_id, "OPEN")
    await _add_alert(patient_id, "RESOLVED")
    survey_day = datetime.now(timezone.utc).date()
    await _add_survey(patient_id, survey_day)

    headers = await _login(client, DOCTOR_PHONE)
    body = (await client.get("/api/v1/dashboard/patients", headers=headers)).json()
    row = next(r for r in body["data"]["content"] if r["patient_id"] == str(patient_id))

    assert row["patient_name"] == "Bệnh nhân A"
    assert row["adherence_rate"] == 50.0  # 2 TAKEN of 4 scheduled
    assert row["open_alerts_count"] == 1  # RESOLVED does not count
    assert row["last_survey_date"] == survey_day.isoformat()


@pytest.mark.asyncio
async def test_acknowledged_alert_still_counts_as_open(client):
    """A doctor having seen an alert does not mean the patient is fine; hiding
    it would make the roster look calmer than it is."""
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, doctor_id)
    await _add_alert(patient_id, "ACKNOWLEDGED")

    headers = await _login(client, DOCTOR_PHONE)
    body = (await client.get("/api/v1/dashboard/patients", headers=headers)).json()
    row = next(r for r in body["data"]["content"] if r["patient_id"] == str(patient_id))
    assert row["open_alerts_count"] == 1


@pytest.mark.asyncio
async def test_roster_returns_pagination_envelope(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, doctor_id)
    headers = await _login(client, DOCTOR_PHONE)
    page = (
        await client.get(
            "/api/v1/dashboard/patients", params={"page": 1, "size": 10}, headers=headers
        )
    ).json()["data"]

    assert page["page_no"] == 1
    assert page["page_size"] == 10
    assert page["total_elements"] == 1
    assert page["total_pages"] == 1
    assert page["last"] is True


@pytest.mark.asyncio
async def test_roster_search_and_alert_status_filters(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, doctor_id)
    headers = await _login(client, DOCTOR_PHONE)

    hit = await client.get(
        "/api/v1/dashboard/patients", params={"search": "Bệnh nhân"}, headers=headers
    )
    assert hit.json()["data"]["total_elements"] == 1

    miss = await client.get(
        "/api/v1/dashboard/patients", params={"search": "zzzz"}, headers=headers
    )
    assert miss.json()["data"]["total_elements"] == 0

    # No alerts exist for this patient yet, so the filter excludes them.
    filtered = await client.get(
        "/api/v1/dashboard/patients", params={"alertStatus": "OPEN"}, headers=headers
    )
    assert filtered.json()["data"]["total_elements"] == 0

    await _add_alert(patient_id, "OPEN")
    now_listed = await client.get(
        "/api/v1/dashboard/patients", params={"alertStatus": "OPEN"}, headers=headers
    )
    assert now_listed.json()["data"]["total_elements"] == 1


@pytest.mark.asyncio
async def test_roster_filters_by_adherence_band(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    low_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân thấp")
    high_id = await _create_patient("0900000019", "Bệnh nhân cao")
    low_rx = await _create_prescription(low_id, doctor_id)
    high_rx = await _create_prescription(high_id, doctor_id)
    # 1/3 ~= 33% -- unambiguously below the LOW band's strict "< 50%" cutoff.
    # Exactly 50% is deliberately NOT "LOW": dashboard/repository.py's
    # adherence_band filter uses strict "<", the same convention
    # AdherenceReviewService.compute_severity mirrors for its own bands, so
    # a boundary value must land consistently on one side across both.
    await _add_doses(low_id, low_rx, ["TAKEN", "MISSED", "MISSED"])
    await _add_doses(high_id, high_rx, ["TAKEN", "TAKEN"])
    headers = await _login(client, DOCTOR_PHONE)

    low = await client.get(
        "/api/v1/dashboard/patients", params={"adherenceBand": "LOW"}, headers=headers
    )
    high = await client.get(
        "/api/v1/dashboard/patients", params={"adherenceBand": "HIGH"}, headers=headers
    )

    assert [row["patient_id"] for row in low.json()["data"]["content"]] == [str(low_id)]
    assert [row["patient_id"] for row in high.json()["data"]["content"]] == [str(high_id)]


@pytest.mark.asyncio
async def test_admin_sees_patients_across_all_doctors(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    await _create_admin(ADMIN_PHONE)
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, doctor_id)
    headers = await _login(client, ADMIN_PHONE)
    body = (await client.get("/api/v1/dashboard/patients", headers=headers)).json()
    assert str(patient_id) in [r["patient_id"] for r in body["data"]["content"]]


# ---------------------------------------------------------------------------
# GET /dashboard/patients/{patient_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_returns_counts_and_recent_alerts(client):
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    rx_id = await _create_prescription(patient_id, doctor_id, status="APPROVED")
    await _create_prescription(patient_id, doctor_id, status="DRAFT")
    await _add_doses(patient_id, rx_id, ["TAKEN", "MISSED"])
    await _add_alert(patient_id, "OPEN")

    headers = await _login(client, DOCTOR_PHONE)
    response = await client.get(
        f"/api/v1/dashboard/patients/{patient_id}", headers=headers
    )
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["patient"]["user_id"] == str(patient_id)
    assert data["patient"]["phone"] == PATIENT_PHONE
    # DRAFT is not in force, so it must not be counted as active.
    assert data["active_prescriptions_count"] == 1
    assert data["adherence_summary"]["total_doses"] == 2
    assert data["adherence_summary"]["taken_doses"] == 1
    assert data["adherence_summary"]["missed_doses"] == 1
    assert data["adherence_summary"]["adherence_rate"] == 50.0
    assert len(data["recent_alerts"]) == 1


@pytest.mark.asyncio
async def test_detail_hides_existence_of_out_of_scope_patient(client):
    """404 rather than 403 — a distinct status would confirm the UUID exists."""
    await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    other_id = await _create_doctor(OTHER_DOCTOR_PHONE, "Dr Dash B", "LIC-DASH-B")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    await _create_prescription(patient_id, other_id)
    headers = await _login(client, DOCTOR_PHONE)
    response = await client.get(
        f"/api/v1/dashboard/patients/{patient_id}", headers=headers
    )
    assert response.status_code == 404

    unknown = await client.get(
        f"/api/v1/dashboard/patients/{uuid.uuid4()}", headers=headers
    )
    assert unknown.status_code == response.status_code


@pytest.mark.asyncio
async def test_detail_rejects_patient_role(client):
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    headers = await _login(client, PATIENT_PHONE)
    response = await client.get(
        f"/api/v1/dashboard/patients/{patient_id}", headers=headers
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# WS /ws/dashboard
# ---------------------------------------------------------------------------
# Driven with the sync TestClient: httpx.AsyncClient speaks HTTP only, and
# starlette's WebSocket test support is the sync one.


def _ws_token(role: str) -> str:
    return create_access_token(
        user_id=str(uuid.uuid4()), role=role, phone_number="+84900700099"
    )


def test_socket_rejects_missing_token():
    """Rejected before accept(), so a caller never sees a socket that opens and
    then dies — 1008 is the policy-violation close."""
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with tc.websocket_connect("/ws/dashboard"):
                pass
    assert exc_info.value.code == 1008


def test_socket_rejects_patient_role():
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with tc.websocket_connect(f"/ws/dashboard?token={_ws_token('PATIENT')}"):
                pass
    assert exc_info.value.code == 1008


def test_patient_socket_rejects_doctor_role():
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with tc.websocket_connect(f"/ws/patient?token={_ws_token('DOCTOR')}"):
                pass
    assert exc_info.value.code == 1008


def test_patient_socket_rejects_missing_token():
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with tc.websocket_connect("/ws/patient"):
                pass
    assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_patient_event_stream_never_yields_another_patients_frame(monkeypatch):
    patient_id = uuid.uuid4()
    own_frame = {
        "event_type": "routine.updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"patient_id": str(patient_id), "updated_at": "2026-08-28T10:00:00+00:00"},
    }

    async def stream():
        yield {
            "event_type": "routine.updated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"patient_id": str(uuid.uuid4())},
        }
        yield own_frame

    monkeypatch.setattr(DashboardEventService, "stream", staticmethod(stream))
    frames = [frame async for frame in DashboardEventService.stream_patient(patient_id)]

    assert frames == [own_frame]


def test_socket_rejects_a_refresh_token():
    """A refresh token carries no role claim and must not open the feed."""
    refresh = create_refresh_token(user_id=str(uuid.uuid4()))
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with tc.websocket_connect(f"/ws/dashboard?token={refresh}"):
                pass
    assert exc_info.value.code == 1008


def _publish_from_test_thread(event_type: str, data: dict) -> None:
    """Call publish_dashboard_event on a client bound to this call's loop.

    The module-level Redis client is a singleton bound to whichever loop first
    built it — here the TestClient's portal loop — so reusing it from
    asyncio.run() fails with "Event loop is closed". Clearing the global forces
    a fresh client for the publish; the subscriber inside the app keeps the old
    one alive through its own pubsub handle, and both reach the same server.
    """

    async def _run() -> None:
        core_redis.redis_client = None
        try:
            await publish_dashboard_event(event_type, data)
        finally:
            if core_redis.redis_client is not None:
                await core_redis.redis_client.aclose()
            core_redis.redis_client = None

    asyncio.run(_run())


def test_admin_socket_delivers_published_frames():
    """End-to-end through Redis: what a write path publishes is what the portal
    receives, in the documented envelope."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/ws/dashboard?token={_ws_token('ADMIN')}") as ws:
            # accept() returns before the pump task has issued SUBSCRIBE, and
            # Redis pub/sub drops anything published to a channel with no
            # subscriber yet — publishing immediately would race that gap.
            time.sleep(0.5)
            _publish_from_test_thread(
                "alert.opened", {"id": "alert-1", "status": "OPEN"}
            )
            frame = ws.receive_json()

    assert frame["event_type"] == "alert.opened"
    assert frame["data"] == {"id": "alert-1", "status": "OPEN"}
    assert frame["timestamp"]


@pytest.mark.parametrize(
    "event_type,data",
    [
        ("alert.updated", {"id": "alert-1", "status": "ACKNOWLEDGED"}),
        ("adherence.updated", {"patient_id": "p-1", "action": "TAKEN"}),
        (
            "schedule.updated",
            {
                "patient_id": "11111111-1111-1111-1111-111111111111",
                "updated_at": "2026-08-28T10:00:00+00:00",
            },
        ),
    ],
)
def test_admin_socket_delivers_every_published_event_type(event_type, data):
    """The four event types the write paths emit all reach the portal through
    the same channel and envelope."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/ws/dashboard?token={_ws_token('ADMIN')}") as ws:
            time.sleep(0.5)
            _publish_from_test_thread(event_type, data)
            frame = ws.receive_json()

    assert frame["event_type"] == event_type
    assert frame["data"] == data


async def _add_doses_at(
    patient_id: uuid.UUID,
    prescription_id: uuid.UUID,
    doses: list[tuple[str, timedelta]],
):
    """Like _add_doses, but the caller places each dose relative to now.

    The adherence denominator turns on whether a dose is due yet, so these
    tests need to straddle the grace window and the future horizon rather than
    dropping everything in the past.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            item = PrescriptionItem(
                prescription_id=prescription_id,
                display_name="Amlodipin 5mg",
                dose_unit="VIEN",
                start_date=datetime.now(timezone.utc).date(),
            )
            db.add(item)
            await db.flush()
            now = datetime.now(timezone.utc)
            for status, offset in doses:
                at = now + offset
                db.add(
                    ScheduledDose(
                        prescription_item_id=item.id,
                        patient_id=patient_id,
                        original_scheduled_at=at,
                        current_scheduled_at=at,
                        status=status,
                        taken_at=at if status == "TAKEN" else None,
                    )
                )


@pytest.mark.asyncio
async def test_future_pending_doses_are_excluded_from_adherence(client):
    """schedule_horizon_days of doses are generated ahead of now. Counting
    them would put a fully adherent patient near 33% on a 7-day window."""
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    rx_id = await _create_prescription(patient_id, doctor_id, status="APPROVED")
    await _add_doses_at(
        patient_id,
        rx_id,
        [
            ("TAKEN", timedelta(hours=-3)),
            ("PENDING", timedelta(hours=2)),
            ("PENDING", timedelta(days=1)),
            ("PENDING", timedelta(days=10)),
        ],
    )

    headers = await _login(client, DOCTOR_PHONE)
    data = (
        await client.get(f"/api/v1/dashboard/patients/{patient_id}", headers=headers)
    ).json()["data"]

    assert data["adherence_summary"]["total_doses"] == 1
    assert data["adherence_summary"]["taken_doses"] == 1
    assert data["adherence_summary"]["adherence_rate"] == 100.0

    row = next(
        r
        for r in (
            await client.get("/api/v1/dashboard/patients", headers=headers)
        ).json()["data"]["content"]
        if r["patient_id"] == str(patient_id)
    )
    assert row["adherence_rate"] == 100.0


@pytest.mark.asyncio
async def test_overdue_pending_dose_counts_as_missed(client):
    """The missed-dose scan lags by up to its interval. A dose past the grace
    window is already missed in substance, so it must not wait for the scan to
    show up in the denominator."""
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    rx_id = await _create_prescription(patient_id, doctor_id, status="APPROVED")
    await _add_doses_at(
        patient_id,
        rx_id,
        [("TAKEN", timedelta(hours=-4)), ("PENDING", timedelta(hours=-3))],
    )

    headers = await _login(client, DOCTOR_PHONE)
    summary = (
        await client.get(f"/api/v1/dashboard/patients/{patient_id}", headers=headers)
    ).json()["data"]["adherence_summary"]

    assert summary["total_doses"] == 2
    assert summary["taken_doses"] == 1
    assert summary["missed_doses"] == 1
    assert summary["adherence_rate"] == 50.0
    # The four figures are shown side by side; they must add up.
    assert (
        summary["taken_doses"] + summary["skipped_doses"] + summary["missed_doses"]
        == summary["total_doses"]
    )


@pytest.mark.asyncio
async def test_pending_dose_inside_grace_window_is_not_counted(client):
    """A dose due minutes ago has not been missed yet — counting it would dip
    the rate every time a dose comes due."""
    doctor_id = await _create_doctor(DOCTOR_PHONE, "Dr Dash A", "LIC-DASH-A")
    patient_id = await _create_patient(PATIENT_PHONE, "Bệnh nhân A")
    rx_id = await _create_prescription(patient_id, doctor_id, status="APPROVED")
    await _add_doses_at(
        patient_id,
        rx_id,
        [("TAKEN", timedelta(hours=-4)), ("PENDING", timedelta(minutes=-5))],
    )

    headers = await _login(client, DOCTOR_PHONE)
    summary = (
        await client.get(f"/api/v1/dashboard/patients/{patient_id}", headers=headers)
    ).json()["data"]["adherence_summary"]

    assert summary["total_doses"] == 1
    assert summary["taken_doses"] == 1
    assert summary["missed_doses"] == 0
    assert summary["adherence_rate"] == 100.0
