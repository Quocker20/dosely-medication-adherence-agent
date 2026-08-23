"""Export a healthy Chroma collection to the exact-cosine dense format."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist-dir", type=Path, required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    collection = chromadb.PersistentClient(path=str(args.persist_dir)).get_collection(
        args.collection
    )
    count = collection.count()
    first = collection.get(limit=1, include=["embeddings"])
    dimensions = len(first["embeddings"][0])
    args.output.mkdir(parents=True, exist_ok=True)
    vectors = np.lib.format.open_memmap(
        args.output / "vectors.npy",
        mode="w+",
        dtype=np.float32,
        shape=(count, dimensions),
    )
    records_tmp = args.output / "records.jsonl.tmp"
    with records_tmp.open("w", encoding="utf-8") as records_file:
        for offset in range(0, count, args.batch_size):
            result = collection.get(
                limit=args.batch_size,
                offset=offset,
                include=["embeddings", "documents", "metadatas"],
            )
            size = len(result["ids"])
            batch_vectors = np.asarray(result["embeddings"], dtype=np.float32)
            batch_vectors /= np.maximum(
                np.linalg.norm(batch_vectors, axis=1, keepdims=True), 1e-12
            )
            vectors[offset : offset + size] = batch_vectors
            for chunk_id, document, metadata in zip(
                result["ids"], result["documents"], result["metadatas"], strict=True
            ):
                records_file.write(
                    json.dumps(
                        {"id": chunk_id, "document": document, "metadata": metadata},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            vectors.flush()
            print(f"{offset + size}/{count}", flush=True)
    records_tmp.replace(args.output / "records.jsonl")
    manifest = {
        "embedding_model": collection.metadata.get(
            "embedding_model", "text-embedding-3-large"
        ),
        "count": count,
        "dimensions": dimensions,
        "source_collection": args.collection,
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Complete: {count} vectors")


if __name__ == "__main__":
    main()
