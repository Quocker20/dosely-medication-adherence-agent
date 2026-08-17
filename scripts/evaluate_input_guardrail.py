from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag_retrieval.input_guardrail import route_input  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic input routing.")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval" / "input_guardrail_cases.json")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        route = route_input(case["input"], recognized_drug=case.get("recognized_drug", False))
        passed = route.intent == case["expected"]
        results.append({"id": case["id"], "passed": passed, "actual": route.intent})
        print(f"{'PASS' if passed else 'FAIL'} {case['id']}: {route.intent}")
    report = {"passed": sum(row["passed"] for row in results), "total": len(results), "results": results}
    output = ROOT / "data" / "rag_corpus_q2" / "input_guardrail_eval_results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
