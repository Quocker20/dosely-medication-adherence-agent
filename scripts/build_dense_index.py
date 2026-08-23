from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "rag_corpus" / "chunks_ready.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "rag_dense_index"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_chunks(path: Path) -> list[dict[str, Any]]:
    chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [
        chunk
        for chunk in chunks
        if chunk.get("review_status") == "approved" and not chunk.get("needs_review")
    ]


def embeddings(client: OpenAI, model: str, texts: list[str], retries: int = 6) -> tuple[np.ndarray, int]:
    for attempt in range(retries + 1):
        try:
            response = client.embeddings.create(model=model, input=texts)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors = np.asarray([item.embedding for item in ordered], dtype=np.float32)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            return vectors, response.usage.prompt_tokens
        except RateLimitError as error:
            if "insufficient_quota" in str(error):
                raise RuntimeError("OpenAI quota exhausted; add credit and rerun to resume") from error
            if attempt == retries:
                raise
        except (APIConnectionError, APITimeoutError):
            if attempt == retries:
                raise
        time.sleep(min(60, 2**attempt + random.random()))
    raise AssertionError("unreachable")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Build a resumable exact-cosine dense index.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="text-embedding-3-large")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    args.output.mkdir(parents=True, exist_ok=True)

    chunks = load_chunks(args.input)
    corpus_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    state_path = args.output / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state and (state.get("corpus_sha256") != corpus_hash or state.get("model") != args.model):
        raise SystemExit("Existing dense-index state belongs to another corpus/model")
    completed = int(state.get("completed_chunks", 0))
    total_tokens = int(state.get("prompt_tokens", 0))
    client = OpenAI(timeout=45.0, max_retries=0)
    vector_path = args.output / "vectors.npy"
    matrix = np.load(vector_path, mmap_mode="r+") if vector_path.exists() else None

    try:
        for start in range(completed, len(chunks), args.batch_size):
            batch = chunks[start : start + args.batch_size]
            vectors, tokens = embeddings(client, args.model, [chunk["embedding_text"] for chunk in batch])
            if matrix is None:
                matrix = np.lib.format.open_memmap(
                    vector_path, mode="w+", dtype=np.float32, shape=(len(chunks), vectors.shape[1])
                )
            if vectors.shape[1] != matrix.shape[1]:
                raise ValueError("Embedding dimension changed")
            matrix[start : start + len(batch)] = vectors
            matrix.flush()
            completed = start + len(batch)
            total_tokens += tokens
            write_json(
                state_path,
                {"status": "running", "model": args.model, "corpus_sha256": corpus_hash, "total_chunks": len(chunks), "completed_chunks": completed, "prompt_tokens": total_tokens, "updated_at": now()},
            )
            print(f"{completed}/{len(chunks)} ({completed / len(chunks):.1%}) | tokens={total_tokens}", flush=True)
    except (Exception, KeyboardInterrupt) as error:
        write_json(state_path, {"status": "stopped", "model": args.model, "corpus_sha256": corpus_hash, "total_chunks": len(chunks), "completed_chunks": completed, "prompt_tokens": total_tokens, "error": type(error).__name__, "updated_at": now()})
        print(f"Stopped at {completed}/{len(chunks)}: {error}", file=sys.stderr)
        return 1

    records_path = args.output / "records.jsonl"
    with records_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            metadata = {key: value for key, value in chunk.items() if key not in {"content", "embedding_text", "review_reasons"} and isinstance(value, (str, int, float, bool))}
            handle.write(json.dumps({"id": chunk["chunk_id"], "document": chunk["embedding_text"], "metadata": metadata}, ensure_ascii=False) + "\n")
    write_json(args.output / "manifest.json", {"embedding_model": args.model, "corpus_sha256": corpus_hash, "count": len(chunks), "dimensions": int(matrix.shape[1]), "created_at": now()})
    write_json(state_path, {"status": "complete", "model": args.model, "corpus_sha256": corpus_hash, "total_chunks": len(chunks), "completed_chunks": len(chunks), "prompt_tokens": total_tokens, "updated_at": now()})
    print(f"Complete: {len(chunks)} vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
