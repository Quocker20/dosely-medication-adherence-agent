from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag_ingestion import pipeline  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Build validated RAG chunks from OCR sidecars.")
    parser.add_argument("--input", type=Path, default=Path("data/ocr_chunks_60"))
    parser.add_argument("--output", type=Path, default=Path("data/rag_corpus"))
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--min-confidence", type=float, default=0.82)
    parser.add_argument(
        "--document-id", default="duoc-thu-quoc-gia-viet-nam-2022-quyen-1"
    )
    parser.add_argument(
        "--source-name", default="Dược thư Quốc gia Việt Nam 2022 - Quyển 1"
    )
    args = parser.parse_args()
    # The ingestion module uses these values when constructing stable chunk IDs
    # and provenance metadata. Set them explicitly for each book volume.
    pipeline.DOCUMENT_ID = args.document_id
    pipeline.SOURCE_NAME = args.source_name
    summary = pipeline.build_corpus(
        args.input, args.output, max_tokens=args.chunk_size,
        overlap_tokens=args.chunk_overlap, min_confidence=args.min_confidence,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
