import pytest

VALID_ITEM = {
    "drug_name": "Amlodipin 5mg",
    "dose_per_intake": "1 viên",
    "frequency_per_day": 1,
    "timing": "AFTER_BREAKFAST",
    "treatment_days": 30,
    "patient_note": "Không dùng chung với nước bưởi",
}


async def _create(client, items):
    response = await client.post("/api/v1/patients/p-01/prescriptions", json={"items": items})
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_new_prescription_starts_as_draft(client):
    data = await _create(client, [VALID_ITEM])
    assert data["status"] == "DRAFT"
    assert data["approved_at"] is None
    assert data["items"][0]["seq"] == 1


@pytest.mark.asyncio
async def test_draft_prescription_has_no_schedule(client):
    draft = await _create(client, [VALID_ITEM])
    response = await client.post(
        "/api/v1/patients/p-01/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    assert response.status_code == 409

    assert (await client.get("/api/v1/patients/p-01/schedules")).status_code == 404


@pytest.mark.asyncio
async def test_approve_then_generate_active_schedule(client):
    draft = await _create(client, [VALID_ITEM])

    approved = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_at"] is not None

    generated = await client.post(
        "/api/v1/patients/p-01/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    assert generated.status_code == 200

    schedule = generated.json()
    assert schedule["status"] == "ACTIVE"
    assert [slot["time"] for slot in schedule["slots"]] == ["07:15"]
    assert schedule["agent_run"]["denied_ops"] == [
        "UPDATE_DOSE",
        "UPDATE_FREQUENCY",
        "UPDATE_ROUTE",
        "UPDATE_DURATION",
    ]


@pytest.mark.asyncio
async def test_validator_blocks_approval_and_lists_issues(client):
    draft = await _create(client, [{**VALID_ITEM, "frequency_per_day": 6}])

    response = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")
    assert response.status_code == 422
    assert response.json()["detail"][0]["code"] == "FREQUENCY_OUT_OF_RANGE"

    still_draft = await client.get(f"/api/v1/prescriptions/{draft['id']}")
    assert still_draft.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_empty_prescription_cannot_be_approved(client):
    draft = await _create(client, [])
    response = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")
    assert response.status_code == 422
    assert response.json()["detail"][0]["code"] == "EMPTY_PRESCRIPTION"


@pytest.mark.asyncio
async def test_approving_twice_is_rejected(client):
    draft = await _create(client, [VALID_ITEM])
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")

    again = await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_bedtime_conflict_returns_needs_review(client):
    item = {**VALID_ITEM, "frequency_per_day": 2, "timing": "BEDTIME"}
    draft = await _create(client, [item])
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")

    generated = await client.post(
        "/api/v1/patients/p-01/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    schedule = generated.json()
    assert schedule["status"] == "NEEDS_REVIEW"
    assert schedule["slots"] == []
    assert schedule["review_notes"]


@pytest.mark.asyncio
async def test_schedule_generation_bumps_version(client):
    draft = await _create(client, [VALID_ITEM])
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")

    first = await client.post(
        "/api/v1/patients/p-01/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    second = await client.post(
        "/api/v1/patients/p-01/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2


@pytest.mark.asyncio
async def test_prescription_of_another_patient_is_forbidden(client):
    draft = await _create(client, [VALID_ITEM])
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")

    response = await client.post(
        "/api/v1/patients/p-02/schedules/generate",
        json={"prescription_id": draft["id"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_endpoint_lets_agent_edit_an_approved_prescription(client):
    """Định nghĩa DoD của API: không có đường nào sửa liều sau khi duyệt."""
    draft = await _create(client, [VALID_ITEM])
    await client.post(f"/api/v1/prescriptions/{draft['id']}/approve")

    for method in ("put", "patch"):
        response = await getattr(client, method)(
            f"/api/v1/prescriptions/{draft['id']}",
            json={"items": [{**VALID_ITEM, "dose_per_intake": "2 viên"}]},
        )
        assert response.status_code == 405
