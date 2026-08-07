import pytest


@pytest.mark.asyncio
async def test_list_alerts_and_filter_by_state(client):
    response = await client.get("/api/v1/alerts")
    assert response.status_code == 200
    assert len(response.json()) == 3

    open_only = await client.get("/api/v1/alerts", params={"state": "OPEN"})
    assert [a["state"] for a in open_only.json()] == ["OPEN", "OPEN"]


@pytest.mark.asyncio
async def test_full_lifecycle_open_to_resolved(client):
    ack = await client.post("/api/v1/alerts/AL-2081/acknowledge")
    assert ack.json()["state"] == "ACKNOWLEDGED"

    resolved = await client.post("/api/v1/alerts/AL-2081/resolve", json={"false_positive": False})
    assert resolved.json()["state"] == "RESOLVED"


@pytest.mark.asyncio
async def test_alert_cannot_be_resolved_before_acknowledge(client):
    response = await client.post("/api/v1/alerts/AL-2081/resolve", json={"false_positive": False})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_acknowledge_twice_is_rejected(client):
    await client.post("/api/v1/alerts/AL-2081/acknowledge")
    again = await client.post("/api/v1/alerts/AL-2081/acknowledge")
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_false_positive_closes_with_distinct_state(client):
    resolved = await client.post("/api/v1/alerts/AL-2079/resolve", json={"false_positive": True})
    assert resolved.json()["state"] == "CLOSED_FALSE_POSITIVE"


@pytest.mark.asyncio
async def test_resolving_alert_lowers_dashboard_open_count(client):
    before = (await client.get("/api/v1/dashboard/summary")).json()["open_alerts"]

    await client.post("/api/v1/alerts/AL-2079/resolve", json={"false_positive": False})
    after = (await client.get("/api/v1/dashboard/summary")).json()["open_alerts"]

    assert after == before - 1


@pytest.mark.asyncio
async def test_unknown_alert_returns_404(client):
    assert (await client.post("/api/v1/alerts/AL-9999/acknowledge")).status_code == 404
