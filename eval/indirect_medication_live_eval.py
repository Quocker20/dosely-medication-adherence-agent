"""Live semantic-classifier evaluation for the indirect-medication golden set."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.nodes.classify_intent_node import classify_intent_node  # noqa: E402


async def main() -> int:
    cases = json.loads((ROOT / "eval" / "indirect_medication_golden_cases.json").read_text(encoding="utf-8"))
    semantic_cases = [case for case in cases if case.get("intent")]
    results = []
    for case in semantic_cases:
        actual = await classify_intent_node({"messages": [HumanMessage(content=case["question"])]})
        analysis = actual.get("intent_analysis") or {}
        expected_topics = set(case.get("topics") or [])
        actual_topics = set(analysis.get("topics") or [])
        results.append({
            "id": case["id"],
            "intent_ok": actual.get("intent") == case["intent"],
            "reference_ok": not case.get("reference_type") or analysis.get("reference_type") == case["reference_type"],
            "topics_ok": expected_topics.issubset(actual_topics),
            "actual_intent": actual.get("intent"),
            "actual_reference": analysis.get("reference_type"),
            "missing_topics": sorted(expected_topics - actual_topics),
        })
    passed = sum(r["intent_ok"] and r["reference_ok"] and r["topics_ok"] for r in results)
    print(json.dumps({"passed": passed, "total": len(results), "cases": results}, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
