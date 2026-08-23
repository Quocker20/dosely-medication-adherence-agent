from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag_retrieval.service import DrugRAG, fold  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate the actual hybrid Chroma retriever.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "drug_rag_questions.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--case-id", help="Run one case while debugging a failed scenario")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    cases = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.case_id:
        cases = [case for case in cases if case["id"] == args.case_id]
        if not cases:
            raise SystemExit(f"Unknown case id: {args.case_id}")
    rag = DrugRAG()
    results = []
    for case in cases:
        hits = rag.retrieve(
            case["question"], top_k=args.top_k, drug=case.get("drug_filter")
        )
        if case.get("expected_empty"):
            passed = not hits
            results.append(
                {"id": case["id"], "passed": passed, "expected_empty": True, "hits": [hit.chunk_id for hit in hits]}
            )
            print(f"{'PASS' if passed else 'FAIL'} {case['id']} -> {[hit.chunk_id for hit in hits]}")
            continue
        combined = fold(" ".join(hit.document for hit in hits))
        expected_drug = fold(case.get("expected_drug", "")).replace(" ", "")
        expected_section = case.get("expected_section")
        drug_ok = not expected_drug or any(
            hit.metadata.get("normalized_drug_name") == expected_drug for hit in hits
        )
        section_ok = not expected_section or any(
            hit.metadata.get("section") == expected_section for hit in hits
        )
        content_ok = all(fold(term) in combined for term in case.get("must_contain", []))
        passed = bool(hits) and drug_ok and section_ok and content_ok
        results.append(
            {
                "id": case["id"],
                "passed": passed,
                "drug_ok": drug_ok,
                "section_ok": section_ok,
                "content_ok": content_ok,
                "hits": [hit.chunk_id for hit in hits],
            }
        )
        print(f"{'PASS' if passed else 'FAIL'} {case['id']} -> {[hit.chunk_id for hit in hits]}")

    passed_count = sum(result["passed"] for result in results)
    report = {
        "passed": passed_count,
        "total": len(results),
        "pass_rate": passed_count / max(len(results), 1),
        "results": results,
    }
    filename = (
        f"retrieval_eval_{args.case_id}.json" if args.case_id else "retrieval_eval_results.json"
    )
    output = ROOT / "data" / "rag_corpus" / filename
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed_count == len(results) else 1)


if __name__ == "__main__":
    main()
