import pytest


@pytest.mark.asyncio
async def test_seeded_patient_schedule_is_ready_for_mobile(client):
    response = await client.get("/api/v1/patients/p-02/schedules")
    assert response.status_code == 200

    schedule = response.json()
    assert schedule["status"] == "ACTIVE"
    assert schedule["slots"][1]["doses"][0]["id"] == "dose-p02-1230-metformin"


@pytest.mark.asyncio
async def test_dose_action_is_idempotent_and_append_only(client):
    headers = {"Idempotency-Key": "dose-action-demo-0001"}
    payload = {"action": "TAKEN", "note": "Đã uống sau bữa trưa"}

    first = await client.post(
        "/api/v1/scheduled-doses/dose-p02-1230-metformin/actions",
        json=payload,
        headers=headers,
    )
    replay = await client.post(
        "/api/v1/scheduled-doses/dose-p02-1230-metformin/actions",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    second_action = await client.post(
        "/api/v1/scheduled-doses/dose-p02-1230-metformin/actions",
        json={"action": "SKIPPED"},
        headers={"Idempotency-Key": "dose-action-demo-0002"},
    )
    assert second_action.status_code == 409


@pytest.mark.asyncio
async def test_dose_action_requires_idempotency_key(client):
    response = await client.post(
        "/api/v1/scheduled-doses/dose-p02-1230-metformin/actions",
        json={"action": "TAKEN"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_severe_survey_opens_doctor_alert(client):
    before = len((await client.get("/api/v1/alerts")).json())
    response = await client.post(
        "/api/v1/patients/p-02/health-surveys",
        json={
            "mood": 2,
            "symptoms": ["Đau ngực"],
            "severity": "SEVERE",
            "note": "Khó chịu tăng dần",
        },
    )
    alerts = (await client.get("/api/v1/alerts")).json()

    assert response.status_code == 201
    assert len(alerts) == before + 1
    assert alerts[-1]["kind"] == "SEVERE_SYMPTOM"
    assert alerts[-1]["state"] == "OPEN"


@pytest.mark.asyncio
async def test_sos_is_idempotent_and_visible_on_portal(client):
    headers = {"Idempotency-Key": "sos-demo-request-0001"}
    payload = {"note": "Đau ngực", "share_location": True}

    first = await client.post("/api/v1/patients/p-02/sos", json=payload, headers=headers)
    replay = await client.post("/api/v1/patients/p-02/sos", json=payload, headers=headers)

    assert first.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    alert_id = first.json()["alert_id"]
    alerts = (await client.get("/api/v1/alerts")).json()
    assert any(alert["id"] == alert_id and alert["kind"] == "SOS" for alert in alerts)


@pytest.mark.asyncio
async def test_patient_adherence_summary_reflects_dose_action(client):
    await client.post(
        "/api/v1/scheduled-doses/dose-p02-1230-losartan/actions",
        json={"action": "LATE"},
        headers={"Idempotency-Key": "dose-action-demo-0003"},
    )
    summary = await client.get("/api/v1/patients/p-02/adherence")

    assert summary.status_code == 200
    assert summary.json()["taken"] == 1
    assert summary.json()["late"] == 1
