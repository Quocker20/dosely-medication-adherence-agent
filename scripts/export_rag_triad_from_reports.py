"""Build a RAG Triad grading bundle offline from completed eval reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_rag_triad_bundle import (  # noqa: E402
    GRADER_INSTRUCTIONS,
    GRADER_OUTPUT_SCHEMA,
    RUBRIC,
)

ID_MAP = {
    "q1-pas": "q1-pas",
    "q1-amoxicilin": "q1-amoxicilin",
    "q2-paracetamol-action": "q2-paracetamol-action",
    "q2-paracetamol-contra": "q2-paracetamol-contra",
    "q2-zolpidem": "q2-zolpidem-interactions",
}


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retrieval-report",
        type=Path,
        default=ROOT / "data" / "rag_corpus" / "retrieval_eval_results.json",
    )
    parser.add_argument(
        "--e2e-report",
        type=Path,
        default=ROOT / "data" / "rag_corpus" / "end_to_end_eval_results.json",
    )
    parser.add_argument(
        "--retrieval-cases",
        type=Path,
        default=ROOT / "eval" / "rag_q1_q2_retrieval_cases.json",
    )
    parser.add_argument(
        "--e2e-cases",
        type=Path,
        default=ROOT / "eval" / "rag_q1_q2_end_to_end_cases.json",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=ROOT / "data" / "rag_dense_index_q1_q2" / "records.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "rag_evaluation" / "rag_triad_bundle_q1_q2.json",
    )
    args = parser.parse_args()

    retrieval_results = {row["id"]: row for row in load_json(args.retrieval_report)["results"]}
    e2e_results = {row["id"]: row for row in load_json(args.e2e_report)["results"]}
    retrieval_cases = {row["id"]: row for row in load_json(args.retrieval_cases)}
    e2e_cases = {row["id"]: row for row in load_json(args.e2e_cases)}
    records = {
        row["id"]: row
        for row in (
            json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line
        )
    }

    cases = []
    for e2e_id, retrieval_id in ID_MAP.items():
        e2e = e2e_results[e2e_id]
        retrieval = retrieval_results[retrieval_id]
        expected = dict(retrieval_cases[retrieval_id])
        expected.update(e2e_cases[e2e_id])
        expected.pop("id", None)
        expected.pop("question", None)
        contexts = []
        for rank, chunk_id in enumerate(retrieval["hits"], start=1):
            record = records[chunk_id]
            metadata = record["metadata"]
            contexts.append(
                {
                    "context_id": f"context-{rank}",
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "citation": (
                        f"{metadata.get('source_name')} — {metadata.get('drug_name')} — "
                        f"{metadata.get('section_label')}, trang {metadata.get('page_start')}"
                    ),
                    "metadata": metadata,
                    "text": record["document"],
                }
            )
        cases.append(
            {
                "id": e2e_id,
                "question": e2e_cases[e2e_id]["question"],
                "expected": expected,
                "retrieved_contexts": contexts,
                "raw_answer": e2e["answer"],
                "final_answer": e2e["answer"],
                "pipeline_status": e2e["status"],
                "pipeline_grounding_valid": e2e["grounding_valid"],
                "pipeline_grounding_errors": e2e["grounding_errors"],
            }
        )

    bundle = {
        "bundle_type": "rag_triad_manual_grading",
        "collection_mode": "offline_from_completed_eval_reports",
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "corpus": "Dược thư Quốc gia Việt Nam 2022, Quyển 1 + Quyển 2",
        "grader_target": "ChatGPT 5.6 (user-selected)",
        "grader_instructions": GRADER_INSTRUCTIONS,
        "rubric": RUBRIC,
        "grader_output_schema": GRADER_OUTPUT_SCHEMA,
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} completed RAG cases to {args.output}")


if __name__ == "__main__":
    main()
