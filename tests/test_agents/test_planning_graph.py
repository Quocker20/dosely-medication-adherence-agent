import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.planning_graph import (
    planning_commit_graph,
    planning_draft_graph,
    planning_snapshot_graph,
)
from src.modules.agents.grouping import DoseGroupingProposal


def _item(*, is_critical: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        medication_id=uuid.uuid4(),
        dose_unit="tablet",
        morning_dose=Decimal("1"),
        noon_dose=None,
        evening_dose=None,
        bedtime_dose=None,
        meal_relation="WITH_MEAL",
        minimum_interval_minutes=60,
        start_date=date(2026, 8, 21),
        end_date=date(2026, 8, 21),
        is_critical=is_critical,
        interval_days=1,
    )


class FakeDoseRepository:
    def __init__(self, item_versions: list[list[SimpleNamespace]]) -> None:
        self.item_versions = item_versions
        self.item_reads = 0
        self.inserted_rows: list[dict] = []
        self.delete_calls = 0

    async def get_patient_context_unscoped(
        self,
        patient_id: uuid.UUID,
        *,
        for_update: bool = False,
    ):
        routine = SimpleNamespace(
            wake_time=time(6),
            breakfast_time=time(8),
            lunch_time=time(12),
            dinner_time=time(18),
            sleep_time=time(23),
        )
        return "Asia/Ho_Chi_Minh", routine

    async def get_approved_items(
        self,
        patient_id: uuid.UUID,
        *,
        for_update: bool = False,
    ):
        index = min(self.item_reads, len(self.item_versions) - 1)
        self.item_reads += 1
        return [(item, uuid.uuid4()) for item in self.item_versions[index]]

    async def lock_reschedule_window(self, patient_id: uuid.UUID, now: datetime):
        return []

    async def get_active_overrides(
        self,
        patient_id: uuid.UUID,
        *,
        start: date,
        end: date,
        for_update: bool = False,
    ):
        return {}

    async def delete_future_pending(self, patient_id: uuid.UUID, now: datetime):
        self.delete_calls += 1

    async def bulk_insert_doses(self, rows: list[dict]) -> int:
        self.inserted_rows = rows
        return len(rows)


def _settings(*, grouping_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        max_frequency_per_day=4,
        schedule_horizon_days=0,
        min_dose_gap_minutes=60,
        max_treatment_days=30,
        jwt_secret_key="test-audit-secret",
        planning_grouping_enabled=grouping_enabled,
        planning_agent_timeout_ms=1000,
        notification_group_window_minutes=30,
        model_name="test-model",
    )


async def _run_graphs(
    repo: FakeDoseRepository,
    settings: SimpleNamespace,
    *,
    is_reschedule: bool = False,
    commit_now: datetime | None = None,
):
    fixed_now = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    config = {
        "configurable": {
            "dose_repo": repo,
            "settings": settings,
            "clock": lambda: commit_now or fixed_now,
        }
    }
    initial = {
        "run_id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "is_reschedule": is_reschedule,
        "run_now": fixed_now,
    }
    snapshot = await planning_snapshot_graph.ainvoke(initial, config=config)
    draft = await planning_draft_graph.ainvoke(snapshot, config=config)
    return await planning_commit_graph.ainvoke(draft, config=config)


@pytest.mark.asyncio
async def test_llm_grouping_changes_notification_metadata_only() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    structured = AsyncMock(
        return_value={
            "parsed": DoseGroupingProposal(groups=[[0, 1]]),
            "raw": SimpleNamespace(response_metadata={"model_name": "served-model-2026"}),
            "parsing_error": None,
        }
    )
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = structured
        final = await _run_graphs(repo, _settings())

    assert final["candidate_source"] == "llm_grouped"
    assert final["llm_model_version"] == "served-model-2026"
    assert len(repo.inserted_rows) == 2
    group_ids = {row["notification_group_id"] for row in repo.inserted_rows}
    assert len(group_ids) == 1
    assert None not in group_ids
    for draft_row, final_row in zip(final["naive_rows_draft"], final["candidate_rows"], strict=True):
        assert final_row.original_scheduled_at == draft_row.original_scheduled_at
        assert final_row.current_scheduled_at == draft_row.current_scheduled_at


@pytest.mark.asyncio
async def test_llm_failure_completes_with_deterministic_fallback() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=TimeoutError)
        final = await _run_graphs(repo, _settings())

    assert final["candidate_source"] == "deterministic_fallback_llm_error"
    assert all(row["notification_group_id"] is None for row in repo.inserted_rows)


@pytest.mark.asyncio
async def test_invalid_llm_group_falls_back_without_changing_doses() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=DoseGroupingProposal(groups=[[0, 0]])
        )
        final = await _run_graphs(repo, _settings())

    assert final["candidate_source"] == "deterministic_fallback_invalid_proposal"
    assert all(row["notification_group_id"] is None for row in repo.inserted_rows)


@pytest.mark.asyncio
async def test_stale_snapshot_rejects_old_llm_proposal() -> None:
    first_items = [_item(), _item()]
    repo = FakeDoseRepository([first_items, [*first_items, _item()]])
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=DoseGroupingProposal(groups=[[0, 1]])
        )
        final = await _run_graphs(repo, _settings())

    assert final["candidate_source"] == "deterministic_fallback_stale_snapshot"
    assert len(repo.inserted_rows) == 3
    assert all(row["notification_group_id"] is None for row in repo.inserted_rows)


@pytest.mark.asyncio
async def test_reschedule_never_calls_llm_or_groups_notifications() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        final = await _run_graphs(repo, _settings(), is_reschedule=True)

    mock_get_llm.assert_not_called()
    assert final["candidate_source"] == "deterministic"
    assert repo.delete_calls == 1


@pytest.mark.asyncio
async def test_disabled_grouping_keeps_deterministic_schedule() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        final = await _run_graphs(repo, _settings(grouping_enabled=False))

    mock_get_llm.assert_not_called()
    assert final["candidate_source"] == "deterministic"
    assert all(row["notification_group_id"] is None for row in repo.inserted_rows)


@pytest.mark.asyncio
async def test_commit_refreshes_clock_and_drops_already_due_rows() -> None:
    repo = FakeDoseRepository([[_item(), _item()]])
    commit_now = datetime(2026, 8, 21, 2, 0, tzinfo=UTC)
    with patch("src.agents.nodes.planning_generate_candidate_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=DoseGroupingProposal(groups=[[0, 1]])
        )
        final = await _run_graphs(repo, _settings(), commit_now=commit_now)

    assert final["candidate_source"] == "deterministic_fallback_stale_snapshot"
    assert repo.inserted_rows == []
