from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag_retrieval import SafeDrugRAG  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run real-model end-to-end RAG evaluation.")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval" / "rag_end_to_end_cases.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    service = SafeDrugRAG()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        result = service.query(case["question"])
        answer_folded = result.answer.casefold()
        content_ok = all(term.casefold() in answer_folded for term in case.get("must_contain", []))
        citation_ok = ("[nguồn" in answer_folded) if case.get("must_cite") else True
        source_ok = not case.get("expected_document_id") or any(
            source.document_id == case["expected_document_id"] for source in result.sources
        )
        passed = (
            result.status == case["expected_status"]
            and content_ok
            and citation_ok
            and source_ok
            and result.grounding_valid
        )
        item = {
            "id": case["id"], "passed": passed, "status": result.status,
            "grounding_valid": result.grounding_valid,
            "grounding_errors": result.grounding_errors,
            "source_count": len(result.sources), "answer": result.answer,
            "source_ok": source_ok,
        }
        results.append(item)
        print(f"{'PASS' if passed else 'FAIL'} {case['id']} [{result.status}] {result.answer}")
    report = {"passed": sum(x["passed"] for x in results), "total": len(results), "results": results}
    output = ROOT / "data" / "rag_corpus" / "end_to_end_eval_results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
