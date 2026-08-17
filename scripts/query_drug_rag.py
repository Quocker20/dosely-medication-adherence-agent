from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag_retrieval import DrugRAG  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Query the local drug-formulary RAG index.")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--drug", help="Exact drug metadata filter")
    parser.add_argument("--section", help="Exact taxonomy section filter")
    parser.add_argument("--retrieve-only", action="store_true")
    parser.add_argument("--answer-model", default="gpt-4o-mini")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    rag = DrugRAG()
    if args.retrieve_only:
        hits = rag.retrieve(
            args.question, top_k=args.top_k, drug=args.drug, section=args.section
        )
        for index, hit in enumerate(hits, start=1):
            print(f"\n[{index}] {hit.citation} | score={hit.score:.6f}")
            print(hit.document)
        raise SystemExit(0 if hits else 1)

    answer, hits = rag.answer(args.question, top_k=args.top_k, model=args.answer_model)
    print(answer)
    print("\nNguồn đã truy xuất:")
    for index, hit in enumerate(hits, start=1):
        print(f"[{index}] {hit.citation} ({hit.chunk_id})")


if __name__ == "__main__":
    main()
