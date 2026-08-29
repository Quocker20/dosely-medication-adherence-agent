"""Golden-set evaluation for PostgreSQL patient context + Dược Thư RAG."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from src.agents.medication_policy import match_medication_decision
from src.agents.nodes import current_medications_node as current_module
from src.agents.nodes import drug_rag_node as drug_rag_module
from src.agents.nodes import explain_my_medications_node as explain_module
from src.agents.nodes import next_dose_node as next_dose_module
from src.agents.nodes import today_schedule_node as today_schedule_module
from src.agents.nodes.classify_intent_node import classify_intent_node
from src.agents.patient_presentation import patient_facing_text
from src.agents.tools.safety_tools import match_severe_symptom_keyword
from src.rag_retrieval import SafeDrugRAG

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "eval" / "hybrid_chat_golden_cases.json"
RESULTS_PATH = ROOT / "data" / "rag_corpus" / "hybrid_chat_eval_results.json"


def _contains_all(text: str, terms: list[str]) -> bool:
    folded = text.casefold()
    return all(term.casefold() in folded for term in terms)


async def _personal_case(case: dict[str, Any]) -> dict[str, Any]:
    state = {"messages": [HumanMessage(content=case["question"])], "patient_id": "golden-user"}
    intent_result = await classify_intent_node(state)

    called_paths: list[str] = []

    async def fake_get(path: str, params: dict | None = None) -> dict:
        called_paths.append(path)
        return case["fixture"]

    original_get = current_module.get
    current_module.get = fake_get
    try:
        node_result = await current_module.current_medications_node(state)
    finally:
        current_module.get = original_get

    answer = str(node_result["messages"][-1].content)
    passed = (
        intent_result.get("intent") == case["expected_intent"]
        and called_paths == ["/patients/me/medications/current"]
        and _contains_all(answer, case.get("must_contain", []))
    )
    return {
        "passed": passed,
        "intent": intent_result.get("intent"),
        "database_paths": called_paths,
        "answer": answer,
    }


async def _explain_medications_case(case: dict[str, Any]) -> dict[str, Any]:
    fixture = case["fixture"]
    state = {
        "messages": [HumanMessage(content=case["question"])],
        "patient_id": "golden-user",
        "client_date": fixture.get("as_of"),
    }
    intent_result = await classify_intent_node(state)
    called_paths: list[str] = []

    def aligned_schedule() -> dict[str, Any]:
        doses = []
        for item in fixture.get("medications", []):
            for slot, field in (("MORNING", "morning_dose"), ("NOON", "noon_dose"), ("EVENING", "evening_dose"), ("BEDTIME", "bedtime_dose")):
                value = item.get(field)
                if value not in (None, "", 0, "0"):
                    doses.append({
                        "prescription_item_id": item.get("id"), "medication_id": item.get("medication_id"),
                        "medication_name": item.get("display_name"), "dose_slot": slot,
                        "dose_value": value, "dose_unit": item.get("dose_unit"),
                        "meal_relation": item.get("meal_relation"),
                    })
        return {"date": fixture.get("as_of"), "doses": doses}

    async def fake_get(path: str, params: dict | None = None) -> dict:
        called_paths.append(path)
        if path == "/patients/me/medications/current":
            if params != {"as_of": fixture.get("as_of")}:
                raise AssertionError(f"unexpected medication params: {params}")
            return fixture
        if path == "/patients/golden-user/schedules":
            if params != {"date": fixture.get("as_of")}:
                raise AssertionError(f"unexpected schedule params: {params}")
            return case.get("schedule_fixture", aligned_schedule())
        raise AssertionError(f"unexpected path: {path}")

    rag_by_drug = case.get("rag_by_drug", {})
    def fake_explain(name: str) -> tuple[str, str]:
        return tuple(rag_by_drug.get(name, ["NO_DATA", "Không tìm thấy thông tin Dược Thư phù hợp."]))

    original_get, original_explain = explain_module.get, explain_module._explain_one
    explain_module.get, explain_module._explain_one = fake_get, fake_explain
    try:
        node_result = await explain_module.explain_my_medications_node(state)
    finally:
        explain_module.get, explain_module._explain_one = original_get, original_explain

    answer = str(node_result["messages"][-1].content)
    passed = (
        intent_result.get("intent") == case["expected_intent"]
        and called_paths == (["/patients/me/medications/current"] if not fixture.get("medications") else ["/patients/me/medications/current", "/patients/golden-user/schedules"])
        and _contains_all(answer, case.get("must_contain", []))
        and not any(term.casefold() in answer.casefold() for term in case.get("must_not_contain", []))
    )
    return {"passed": passed, "intent": intent_result.get("intent"), "database_paths": called_paths, "answer": answer}


async def _schedule_case(case: dict[str, Any], *, next_dose: bool) -> dict[str, Any]:
    fixture = case["fixture"]
    state = {
        "messages": [HumanMessage(content=case["question"])],
        "patient_id": "golden-user",
        "client_date": str(fixture.get("date", "2026-08-29")),
        "client_datetime": case.get("client_datetime", "2026-08-29T18:00:00+07:00"),
    }
    intent_result = await classify_intent_node(state)
    module = next_dose_module if next_dose else today_schedule_module
    endpoint = "/patients/golden-user/schedules"
    called_paths: list[str] = []

    async def fake_get(path: str, params: dict | None = None) -> dict:
        called_paths.append(path)
        if params != {"date": state["client_date"]}:
            raise AssertionError(f"unexpected schedule params: {params}")
        return fixture

    original_get = module.get
    module.get = fake_get
    try:
        node_result = (
            await module.next_dose_node(state)
            if next_dose
            else await module.today_schedule_node(state)
        )
    finally:
        module.get = original_get

    answer = str(node_result["messages"][-1].content)
    passed = (
        intent_result.get("intent") == case["expected_intent"]
        and called_paths == [endpoint]
        and _contains_all(answer, case.get("must_contain", []))
        and not any(term.casefold() in answer.casefold() for term in case.get("must_not_contain", []))
    )
    return {
        "passed": passed,
        "intent": intent_result.get("intent"),
        "database_paths": called_paths,
        "answer": answer,
    }


def _intent_metrics(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (case["expected_intent"], result.get("intent"))
        for case, result in zip(cases, results, strict=True)
        if case.get("expected_intent") is not None and result.get("intent") is not None
    ]
    if not pairs:
        return {"accuracy": None, "macro_precision": None, "macro_recall": None, "macro_f1": None}

    labels = sorted({expected for expected, _ in pairs} | {actual for _, actual in pairs})
    scores: dict[str, dict[str, float | int]] = {}
    for label in labels:
        tp = sum(expected == label and actual == label for expected, actual in pairs)
        fp = sum(expected != label and actual == label for expected, actual in pairs)
        fn = sum(expected == label and actual != label for expected, actual in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores[label] = {
            "support": sum(expected == label for expected, _ in pairs),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return {
        "accuracy": round(sum(expected == actual for expected, actual in pairs) / len(pairs), 4),
        "macro_precision": round(sum(item["precision"] for item in scores.values()) / len(scores), 4),
        "macro_recall": round(sum(item["recall"] for item in scores.values()) / len(scores), 4),
        "macro_f1": round(sum(item["f1"] for item in scores.values()) / len(scores), 4),
        "labels": scores,
        "sample_count": len(pairs),
    }


def _binary_metrics(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    expected_key: str,
    actual_key: str,
) -> dict[str, Any]:
    pairs = [
        (bool(case[expected_key]), bool(result[actual_key]))
        for case, result in zip(cases, results, strict=True)
        if expected_key in case and actual_key in result
    ]
    if not pairs:
        return {"precision": None, "recall": None, "f1": None, "sample_count": 0}
    tp = sum(expected and actual for expected, actual in pairs)
    fp = sum(not expected and actual for expected, actual in pairs)
    fn = sum(expected and not actual for expected, actual in pairs)
    tn = sum(not expected and not actual for expected, actual in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positives": fp,
        "false_negatives": fn,
        "true_positives": tp,
        "true_negatives": tn,
        "sample_count": len(pairs),
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"average": None, "p95": None, "maximum": None}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.9999) - 1))
    return {
        "average": round(sum(ordered) / len(ordered), 2),
        "p95": round(ordered[p95_index], 2),
        "maximum": round(ordered[-1], 2),
    }


def _mode_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for mode in sorted({item["mode"] for item in results}):
        group = [item for item in results if item["mode"] == mode]
        evaluated = [item for item in group if item.get("passed") is not None]
        passed = sum(item.get("passed") is True for item in evaluated)
        report[mode] = {
            "passed": passed,
            "evaluated": len(evaluated),
            "skipped": len(group) - len(evaluated),
            "pass_rate": round(passed / len(evaluated), 4) if evaluated else None,
            "latency_ms": _latency_summary(
                [float(item["latency_ms"]) for item in evaluated]
            ),
        }
    return report


async def _rag_case(case: dict[str, Any], rag: SafeDrugRAG) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(rag.query, case["question"])
    except Exception as exc:  # keep the report useful when the embedding/model service is down
        return {
            "passed": False,
            "status": "infrastructure_error",
            "error": f"{type(exc).__name__}: {exc}",
            "answer": "",
        }
    displayed_answer = patient_facing_text(result.answer)
    topic = drug_rag_module._drug_topic(case["question"])
    if result.status == "answered" and result.grounding_valid and topic:
        names = list(dict.fromkeys(source.drug_name for source in result.sources if source.drug_name))
        displayed_answer = drug_rag_module._format_topic_answer(
            result.answer, ", ".join(names), *topic
        )
    citation_ok = not case.get("must_cite") or "[nguồn" in result.answer.casefold()
    passed = (
        result.status == case["expected_status"]
        and result.grounding_valid
        and citation_ok
        and _contains_all(displayed_answer, case.get("must_contain", []))
        and not any(term.casefold() in displayed_answer.casefold() for term in case.get("must_not_contain", []))
    )
    return {
        "passed": passed,
        "status": result.status,
        "grounding_valid": result.grounding_valid,
        "source_count": len(result.sources),
        "answer": displayed_answer,
    }


async def main(*, skip_live_rag: bool = False) -> None:
    load_dotenv(ROOT / ".env")
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    rag = SafeDrugRAG() if any(case["mode"] == "rag" for case in cases) else None
    results = []

    for case in cases:
        started = time.perf_counter()
        mode = case["mode"]
        if mode == "personal_medications":
            details = await _personal_case(case)
        elif mode == "explain_my_medications":
            details = await _explain_medications_case(case)
        elif mode == "today_schedule":
            details = await _schedule_case(case, next_dose=False)
        elif mode == "next_dose":
            details = await _schedule_case(case, next_dose=True)
        elif mode == "rag" and skip_live_rag:
            details = {
                "passed": None,
                "skipped": True,
                "status": "skipped_live_infrastructure",
            }
        elif mode == "rag":
            details = await _rag_case(case, rag)
        elif mode == "medication_policy":
            blocked = match_medication_decision(case["question"]) is not None
            details = {"passed": blocked == case["expected_blocked"], "blocked": blocked}
        elif mode == "emergency_keyword":
            emergency = match_severe_symptom_keyword(case["question"]) is not None
            details = {
                "passed": emergency == case["expected_emergency"],
                "emergency": emergency,
            }
        else:
            details = {"passed": False, "error": f"Unknown mode: {mode}"}

        item = {
            "id": case["id"],
            "mode": mode,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            **details,
        }
        results.append(item)
        outcome = "SKIP" if item["passed"] is None else ("PASS" if item["passed"] else "FAIL")
        print(f"{outcome} {case['id']} [{mode}]")

    evaluated = [item for item in results if item.get("passed") is not None]
    passed = sum(item.get("passed") is True for item in evaluated)
    report = {
        "passed": passed,
        "total": len(results),
        "evaluated": len(evaluated),
        "skipped": len(results) - len(evaluated),
        "pass_rate": round(passed / len(evaluated), 4) if evaluated else None,
        "intent_metrics": _intent_metrics(cases, results),
        "medication_policy_metrics": _binary_metrics(
            cases, results, expected_key="expected_blocked", actual_key="blocked"
        ),
        "emergency_metrics": _binary_metrics(
            cases, results, expected_key="expected_emergency", actual_key="emergency"
        ),
        "mode_metrics": _mode_metrics(results),
        "latency_ms": _latency_summary(
            [float(item["latency_ms"]) for item in evaluated]
        ),
        "results": results,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TOTAL {report['passed']}/{report['evaluated']} ({report['skipped']} skipped)")
    raise SystemExit(0 if report["passed"] == report["evaluated"] else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the RemindRx hybrid chatbot")
    parser.add_argument(
        "--skip-live-rag",
        action="store_true",
        help="Evaluate deterministic hybrid paths without calling OpenAI",
    )
    args = parser.parse_args()
    asyncio.run(main(skip_live_rag=args.skip_live_rag))
