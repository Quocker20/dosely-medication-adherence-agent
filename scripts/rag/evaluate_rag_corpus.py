from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


def fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def terms(value: str) -> set[str]:
    return {word for word in fold(value).split() if len(word) > 2}


def drug_key(value: str) -> str:
    return fold(value).replace(" ", "")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate metadata-filtered lexical retrieval.")
    parser.add_argument("--chunks", type=Path, default=Path("data/rag_corpus/chunks_ready.jsonl"))
    parser.add_argument("--questions", type=Path, default=Path("eval/drug_rag_questions.json"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    chunks = load_jsonl(args.chunks)
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    passed = 0
    results = []
    for case in questions:
        candidates = [
            chunk for chunk in chunks
            if (not case.get("expected_drug") or chunk["normalized_drug_name"] == drug_key(case["expected_drug"]))
            and (not case.get("expected_section") or chunk["section"] == case["expected_section"])
            and chunk["review_status"] == "approved"
        ]
        query_terms = terms(case["question"])
        ranked = sorted(
            candidates,
            key=lambda chunk: len(query_terms & terms(chunk["embedding_text"])),
            reverse=True,
        )[: args.top_k]
        combined = fold(" ".join(chunk["content"] for chunk in ranked))
        must_contain = [fold(item) for item in case.get("must_contain", [])]
        ok = bool(ranked) and all(item in combined for item in must_contain)
        passed += int(ok)
        results.append({
            "id": case["id"], "passed": ok,
            "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in ranked],
        })
        print(f"{'PASS' if ok else 'FAIL'} {case['id']}: {case['question']}")

    report = {"passed": passed, "total": len(questions), "pass_rate": passed / max(len(questions), 1), "results": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(questions) else 1)


if __name__ == "__main__":
    main()
