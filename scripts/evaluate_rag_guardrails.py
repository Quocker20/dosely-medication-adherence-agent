from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.medication_policy import match_medication_decision  # noqa: E402
from src.agents.nodes.grounding_validator_node import validate_grounded_answer  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate deterministic RAG guardrails.")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval" / "rag_guardrail_cases.json")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        if case["type"] == "safety":
            actual = match_medication_decision(case["input"])
            passed = actual == case["expected"]
        elif case["type"] == "allowed":
            actual = match_medication_decision(case["input"])
            passed = actual is None
        else:
            sources = {int(key): value for key, value in case["sources"].items()}
            validation = validate_grounded_answer(case["answer"], sources)
            actual = validation.valid
            passed = actual is case["valid"]
        results.append({"id": case["id"], "type": case["type"], "passed": passed, "actual": actual})
        print(f"{'PASS' if passed else 'FAIL'} {case['id']} ({case['type']}): {actual}")
    counts = Counter(result["type"] for result in results)
    passed_counts = Counter(result["type"] for result in results if result["passed"])
    report = {
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "by_type": {key: {"passed": passed_counts[key], "total": count} for key, count in counts.items()},
        "results": results,
    }
    output = ROOT / "data" / "rag_corpus" / "guardrail_eval_results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
