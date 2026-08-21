import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.modules.agents.grouping import (
    DoseGroupingProposal,
    GroupingRejectedError,
    apply_dose_grouping,
)
from src.modules.agents.planner import ScheduleRow


def _row(
    *,
    item_id: uuid.UUID | None = None,
    scheduled_at: datetime | None = None,
) -> ScheduleRow:
    timestamp = scheduled_at or datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    return ScheduleRow(
        prescription_item_id=item_id or uuid.uuid4(),
        medication_id=uuid.uuid4(),
        dose_slot="MORNING",
        dose_value=Decimal("1"),
        dose_unit="tablet",
        meal_relation="WITH_MEAL",
        original_scheduled_at=timestamp,
        current_scheduled_at=timestamp,
    )


def test_grouping_sets_one_notification_id_without_changing_schedule() -> None:
    rows = [_row(), _row()]

    grouped = apply_dose_grouping(
        rows,
        DoseGroupingProposal(groups=[[0, 1]]),
        window_minutes=30,
        patient_timezone="Asia/Ho_Chi_Minh",
    )

    assert grouped[0].notification_group_id is not None
    assert grouped[0].notification_group_id == grouped[1].notification_group_id
    for original, candidate in zip(rows, grouped, strict=True):
        assert candidate.original_scheduled_at == original.original_scheduled_at
        assert candidate.current_scheduled_at == original.current_scheduled_at
        assert candidate.dose_value == original.dose_value
        assert candidate.prescription_item_id == original.prescription_item_id


@pytest.mark.parametrize(
    "groups",
    [
        [[0]],
        [[0, 0]],
        [[0, 2]],
        [[0, 1], [1, 0]],
    ],
)
def test_grouping_rejects_invalid_index_structures(groups: list[list[int]]) -> None:
    with pytest.raises(GroupingRejectedError):
        apply_dose_grouping(
            [_row(), _row()],
            DoseGroupingProposal(groups=groups),
            window_minutes=30,
            patient_timezone="Asia/Ho_Chi_Minh",
        )


def test_grouping_rejects_two_doses_from_same_prescription_item() -> None:
    item_id = uuid.uuid4()
    with pytest.raises(GroupingRejectedError):
        apply_dose_grouping(
            [_row(item_id=item_id), _row(item_id=item_id)],
            DoseGroupingProposal(groups=[[0, 1]]),
            window_minutes=30,
            patient_timezone="Asia/Ho_Chi_Minh",
        )


def test_grouping_rejects_cross_local_day_even_inside_time_window() -> None:
    rows = [
        _row(scheduled_at=datetime(2026, 8, 21, 16, 55, tzinfo=UTC)),
        _row(scheduled_at=datetime(2026, 8, 21, 17, 5, tzinfo=UTC)),
    ]
    with pytest.raises(GroupingRejectedError):
        apply_dose_grouping(
            rows,
            DoseGroupingProposal(groups=[[0, 1]]),
            window_minutes=30,
            patient_timezone="Asia/Ho_Chi_Minh",
        )


def test_grouping_rejects_rows_outside_notification_window() -> None:
    rows = [
        _row(scheduled_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC)),
        _row(scheduled_at=datetime(2026, 8, 21, 1, 31, tzinfo=UTC)),
    ]
    with pytest.raises(GroupingRejectedError):
        apply_dose_grouping(
            rows,
            DoseGroupingProposal(groups=[[0, 1]]),
            window_minutes=30,
            patient_timezone="Asia/Ho_Chi_Minh",
        )


def test_grouping_rejects_nearby_but_non_identical_due_times() -> None:
    rows = [
        _row(scheduled_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC)),
        _row(scheduled_at=datetime(2026, 8, 21, 1, 5, tzinfo=UTC)),
    ]
    with pytest.raises(GroupingRejectedError):
        apply_dose_grouping(
            rows,
            DoseGroupingProposal(groups=[[0, 1]]),
            window_minutes=30,
            patient_timezone="Asia/Ho_Chi_Minh",
        )
