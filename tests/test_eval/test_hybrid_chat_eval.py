import json
from pathlib import Path

import pytest

from eval.hybrid_chat_eval import _intent_metrics, _schedule_case

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "eval" / "hybrid_chat_golden_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["mode"] in {"today_schedule", "next_dose"}],
    ids=lambda case: case["id"],
)
async def test_schedule_golden_cases_are_database_scoped_and_well_formatted(case):
    result = await _schedule_case(case, next_dose=case["mode"] == "next_dose")
    assert result["passed"], result


def test_intent_metrics_compute_accuracy_precision_recall_and_f1():
    cases = [
        {"expected_intent": "ask_schedule"},
        {"expected_intent": "ask_schedule"},
        {"expected_intent": "ask_next_dose"},
    ]
    results = [
        {"intent": "ask_schedule"},
        {"intent": "ask_next_dose"},
        {"intent": "ask_next_dose"},
    ]

    metrics = _intent_metrics(cases, results)

    assert metrics["accuracy"] == 0.6667
    assert metrics["sample_count"] == 3
    assert set(metrics["labels"]) == {"ask_schedule", "ask_next_dose"}
    assert 0 <= metrics["macro_precision"] <= 1
    assert 0 <= metrics["macro_recall"] <= 1
    assert 0 <= metrics["macro_f1"] <= 1
