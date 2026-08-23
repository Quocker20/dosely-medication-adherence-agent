"""Merge validated JSONL corpora while rejecting duplicate chunk IDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    count = 0
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        for source in args.inputs:
            with source.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    chunk_id = str(record.get("chunk_id", ""))
                    if not chunk_id:
                        raise ValueError(f"Missing chunk_id: {source}:{line_number}")
                    if chunk_id in seen:
                        raise ValueError(f"Duplicate chunk_id: {chunk_id}")
                    seen.add(chunk_id)
                    destination.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
    temporary.replace(args.output)
    print(f"Merged {count} chunks from {len(args.inputs)} corpora into {args.output}")


if __name__ == "__main__":
    main()
