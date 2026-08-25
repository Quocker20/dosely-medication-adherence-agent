"""Golden-set evaluation for PostgreSQL patient context + Dược Thư RAG."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from src.agents.medication_policy import match_medication_decision
from src.agents.nodes.classify_intent_node import classify_intent_node
from src.agents.nodes import current_medications_node as current_module
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
    citation_ok = not case.get("must_cite") or "[nguồn" in result.answer.casefold()
    passed = (
        result.status == case["expected_status"]
        and result.grounding_valid
        and citation_ok
        and _contains_all(result.answer, case.get("must_contain", []))
    )
    return {
        "passed": passed,
        "status": result.status,
        "grounding_valid": result.grounding_valid,
        "source_count": len(result.sources),
        "answer": result.answer,
    }


async def main() -> None:
    load_dotenv(ROOT / ".env")
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    rag = SafeDrugRAG() if any(case["mode"] == "rag" for case in cases) else None
    results = []

    for case in cases:
        mode = case["mode"]
        if mode == "personal_medications":
            details = await _personal_case(case)
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

        item = {"id": case["id"], "mode": mode, **details}
        results.append(item)
        print(f"{'PASS' if item['passed'] else 'FAIL'} {case['id']} [{mode}]")

    report = {
        "passed": sum(item["passed"] for item in results),
        "total": len(results),
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TOTAL {report['passed']}/{report['total']}")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
