"""Export a self-contained RAG Triad bundle for external manual grading."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.nodes.grounding_validator_node import validate_grounded_answer  # noqa: E402
from src.rag_retrieval.safe_service import _GROUNDING_FALLBACK, _NO_DATA_REPLY  # noqa: E402
from src.rag_retrieval.service import DrugRAG  # noqa: E402

RUBRIC = {
    "scale": "Each dimension is scored from 0.0 to 1.0.",
    "context_relevance": {
        "definition": "How relevant each retrieved context is to the question.",
        "scoring": {
            "1.0": "All contexts directly help answer the question.",
            "0.5": "A mixture of useful and irrelevant contexts.",
            "0.0": "No context helps answer the question.",
        },
        "required_checks": [
            "Label every context relevant or irrelevant.",
            "Check drug, section, volume and requested subject/object direction.",
        ],
    },
    "groundedness": {
        "definition": "Whether every medical claim in raw_answer is entailed by retrieved contexts.",
        "scoring": {
            "1.0": "Every medical claim is supported and all numbers/directions are preserved.",
            "0.5": "Mostly supported with minor unsupported detail.",
            "0.0": "Core claims are unsupported, contradicted, or reverse an interaction.",
        },
        "required_checks": [
            "Split the answer into atomic claims.",
            "Identify supporting context IDs for every claim.",
            "Treat unsupported numbers, dose, ATC or reversed interactions as critical errors.",
        ],
    },
    "answer_relevance": {
        "definition": "Whether raw_answer directly and sufficiently answers the question.",
        "scoring": {
            "1.0": "Direct, focused and sufficiently complete.",
            "0.5": "Partially answers or contains substantial irrelevant material.",
            "0.0": "Does not answer the question.",
        },
    },
    "thresholds": {
        "context_relevance": 0.7,
        "groundedness": 0.9,
        "answer_relevance": 0.8,
        "critical_medical_cases_groundedness": 1.0,
    },
}

GRADER_INSTRUCTIONS = (
    "Evaluate every case using only the retrieved_contexts in this file; do not use outside "
    "medical knowledge. Score the three RAG Triad dimensions independently. For expected_empty "
    "cases, empty retrieval plus an explicit abstention is correct. Return JSON only and follow "
    "grader_output_schema exactly. Preserve Vietnamese text in evidence and error descriptions."
)

GRADER_OUTPUT_SCHEMA = {
    "summary": {
        "case_count": "integer",
        "context_relevance_mean": "number 0..1",
        "groundedness_mean": "number 0..1",
        "answer_relevance_mean": "number 0..1",
        "passed": "integer",
        "failed": "integer",
    },
    "cases": [
        {
            "id": "string",
            "context_relevance": "number 0..1",
            "groundedness": "number 0..1",
            "answer_relevance": "number 0..1",
            "pass": "boolean",
            "context_labels": [{"context_id": "string", "relevant": "boolean", "reason": "string"}],
            "claim_checks": [
                {
                    "claim": "string",
                    "supported": "boolean",
                    "supporting_context_ids": ["string"],
                    "reason": "string",
                }
            ],
            "critical_errors": ["string"],
            "notes": "string",
        }
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "eval" / "rag_q1_q2_retrieval_cases.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "rag_evaluation" / "rag_triad_bundle_q1_q2.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--answer-model", default="gpt-4o-mini")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    rag = DrugRAG()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    exported = []
    for number, case in enumerate(cases, start=1):
        hits = rag.retrieve(case["question"], top_k=args.top_k, drug=case.get("drug_filter"))
        sources = {
            index: f"[Nguồn {index}] {hit.citation}\n{hit.document}"
            for index, hit in enumerate(hits, start=1)
        }
        if hits:
            raw_answer = rag.answer_from_hits(case["question"], hits, model=args.answer_model)
            validation = validate_grounded_answer(raw_answer, sources)
            final_answer = raw_answer if validation.valid else _GROUNDING_FALLBACK
            status = "answered" if validation.valid else "grounding_blocked"
        else:
            raw_answer = _NO_DATA_REPLY
            final_answer = raw_answer
            validation = validate_grounded_answer(raw_answer, {})
            status = "no_data"
        exported.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected": {
                    key: value for key, value in case.items() if key not in {"id", "question"}
                },
                "retrieved_contexts": [
                    {
                        "context_id": f"context-{index}",
                        "rank": index,
                        "chunk_id": hit.chunk_id,
                        "score": hit.score,
                        "citation": hit.citation,
                        "metadata": hit.metadata,
                        "text": hit.document,
                    }
                    for index, hit in enumerate(hits, start=1)
                ],
                "raw_answer": raw_answer,
                "final_answer": final_answer,
                "pipeline_status": status,
                "pipeline_grounding_valid": validation.valid,
                "pipeline_grounding_errors": validation.errors,
            }
        )
        print(f"{number}/{len(cases)} {case['id']} [{status}]", flush=True)

    bundle = {
        "bundle_type": "rag_triad_manual_grading",
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "corpus": "Dược thư Quốc gia Việt Nam 2022, Quyển 1 + Quyển 2",
        "retrieval_top_k": args.top_k,
        "answer_model": args.answer_model,
        "grader_target": "ChatGPT 5.6 (user-selected)",
        "grader_instructions": GRADER_INSTRUCTIONS,
        "rubric": RUBRIC,
        "grader_output_schema": GRADER_OUTPUT_SCHEMA,
        "cases": exported,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(exported)} cases to {args.output}")


if __name__ == "__main__":
    main()
