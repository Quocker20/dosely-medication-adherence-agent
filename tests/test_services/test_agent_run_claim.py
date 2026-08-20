import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql import visitors

from src.modules.agents.repository import AgentRunRepository


@pytest.mark.asyncio
async def test_claim_run_is_a_single_running_unclaimed_compare_and_swap() -> None:
    claimed = SimpleNamespace(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = claimed
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    repository = AgentRunRepository(db)

    returned = await repository.claim_run(claimed.id, lease_seconds=180)

    assert returned is claimed
    statement = db.execute.await_args.args[0]
    assert len(statement._where_criteria) == 3
    assert {column.key for column in statement._values} == {
        "started_at",
        "claim_token",
        "claim_expires_at",
    }
    where_columns = {
        element.key
        for criterion in statement._where_criteria
        for element in visitors.iterate(criterion)
        if getattr(element, "key", None)
    }
    assert "claim_expires_at" in where_columns
    assert statement._returning


@pytest.mark.asyncio
async def test_renew_claim_is_token_scoped_for_safe_recovery() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    repository = AgentRunRepository(db)

    renewed = await repository.renew_claim(uuid.uuid4(), uuid.uuid4(), lease_seconds=180)

    assert renewed is True
    statement = db.execute.await_args.args[0]
    where_columns = {
        element.key
        for criterion in statement._where_criteria
        for element in visitors.iterate(criterion)
        if getattr(element, "key", None)
    }
    assert {"id", "status", "claim_token"}.issubset(where_columns)
