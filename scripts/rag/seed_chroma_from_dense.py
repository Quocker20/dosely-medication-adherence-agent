"""Seed a Chroma collection from an existing exact-cosine dense index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import chromadb
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dense-index", type=Path, required=True)
    parser.add_argument("--persist-dir", type=Path, required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    manifest = json.loads((args.dense_index / "manifest.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (args.dense_index / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    vectors = np.load(args.dense_index / "vectors.npy", mmap_mode="r")
    if len(records) != len(vectors) or len(records) != manifest["count"]:
        raise SystemExit("Dense records, vectors, and manifest count do not match")

    client = chromadb.PersistentClient(path=str(args.persist_dir))
    collection = client.get_or_create_collection(
        name=args.collection,
        metadata={
            "embedding_model": manifest["embedding_model"],
            "source": "duoc_thu_2022_q1_q2",
            "hnsw:space": "cosine",
        },
    )
    for start in range(0, len(records), args.batch_size):
        batch = records[start : start + args.batch_size]
        ids = [record["id"] for record in batch]
        existing = set(collection.get(ids=ids, include=[]).get("ids", []))
        pending_indexes = [index for index, record in enumerate(batch) if record["id"] not in existing]
        if pending_indexes:
            collection.upsert(
                ids=[batch[index]["id"] for index in pending_indexes],
                embeddings=np.asarray(vectors[start : start + len(batch)])[pending_indexes].tolist(),
                documents=[batch[index]["document"] for index in pending_indexes],
                metadatas=[batch[index]["metadata"] for index in pending_indexes],
            )
        print(f"{min(start + len(batch), len(records))}/{len(records)}", flush=True)
    print(f"Complete: collection_count={collection.count()}")


if __name__ == "__main__":
    main()
