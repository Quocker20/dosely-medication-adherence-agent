"""SEC-18: X-Request-ID is client-supplied, so it is validated before reuse."""

import re
import uuid

import pytest

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.mark.asyncio
async def test_generates_uuid_when_header_absent(client):
    response = await client.get("/health")
    assert UUID_RE.match(response.headers["X-Request-ID"])


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [str(uuid.uuid4()), "abc-123", "A" * 64])
async def test_valid_ids_are_echoed(client, value):
    response = await client.get("/health", headers={"X-Request-ID": value})
    assert response.headers["X-Request-ID"] == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    ["A" * 65, "has space", "semi;colon", "new\tline", "../../etc", "<script>", ""],
)
async def test_invalid_ids_are_replaced(client, value):
    response = await client.get("/health", headers={"X-Request-ID": value})
    got = response.headers["X-Request-ID"]
    assert got != value
    assert UUID_RE.match(got)
