import pytest


@pytest.mark.asyncio
async def test_summary_reports_live_alerts_and_average(client):
    response = await client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200

    data = response.json()
    assert data["patients_total"] == 5
    assert data["adherence_avg"] == 69  # (41+55+69+94+88)/5
    assert data["open_alerts"] == 3


@pytest.mark.asyncio
async def test_patients_sorted_with_red_alert_first(client):
    response = await client.get("/api/v1/dashboard/patients")
    assert response.status_code == 200

    statuses = [p["status"] for p in response.json()]
    assert statuses[0] == "RED_ALERT"
    assert statuses[-1] == "STABLE"


@pytest.mark.asyncio
async def test_patient_detail_returns_week_grid_and_logs(client):
    response = await client.get("/api/v1/dashboard/patients/p-01")
    assert response.status_code == 200

    data = response.json()
    assert data["patient"]["name"] == "Trần Thị H."
    assert len(data["week"]) == 14
    assert len(data["logs"]) == 3


@pytest.mark.asyncio
async def test_unknown_patient_returns_404(client):
    response = await client.get("/api/v1/dashboard/patients/p-99")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_routine_update_round_trip(client):
    payload = {"wake": "05:00", "breakfast": "06:00", "lunch": "11:00", "dinner": "17:30", "sleep": "21:00"}
    response = await client.put("/api/v1/patients/p-01/routine", json=payload)
    assert response.status_code == 200
    assert response.json()["breakfast"] == "06:00"

    read_back = await client.get("/api/v1/patients/p-01/routine")
    assert read_back.json()["breakfast"] == "06:00"


@pytest.mark.asyncio
async def test_routine_rejects_bad_time_format(client):
    payload = {"wake": "5h sáng", "breakfast": "06:00", "lunch": "11:00", "dinner": "17:30", "sleep": "21:00"}
    response = await client.put("/api/v1/patients/p-01/routine", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_drug_catalog_search(client):
    response = await client.get("/api/v1/drugs", params={"q": "met"})
    assert response.status_code == 200
    assert [d["brand_name"] for d in response.json()] == ["Metformin 500mg"]
