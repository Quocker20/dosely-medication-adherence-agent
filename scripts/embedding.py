"""Embed approved drug chunks into a persistent Chroma collection.

Safe to stop and run again: existing chunk IDs are skipped and writes use upsert.
Only chunks whose review_status is ``approved`` and needs_review is false are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "rag_corpus" / "chunks_ready.jsonl"
DEFAULT_DB = ROOT / "data" / "chroma"
DEFAULT_STATE = ROOT / "data" / "rag_corpus" / "embedding_state.json"
DEFAULT_MODEL = "text-embedding-3-large"
DEFAULT_COLLECTION = "duoc_thu_2022_q1_te3large_v1"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


def batched(items: list[Chunk], size: int) -> Iterable[list[Chunk]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def scalar_metadata(record: dict[str, Any], model: str, corpus_sha256: str) -> dict[str, Any]:
    fields = (
        "document_id",
        "source_name",
        "drug_name",
        "normalized_drug_name",
        "section",
        "section_label",
        "page_start",
        "page_end",
        "chunk_index",
        "token_count",
        "ocr_confidence",
        "drug_confidence",
        "section_confidence",
        "parser_confidence",
        "review_status",
    )
    metadata = {key: record[key] for key in fields if record.get(key) is not None}
    metadata.update(
        {
            "embedding_model": model,
            "corpus_sha256": corpus_sha256,
            "indexed_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        }
    )
    return metadata


def load_approved_chunks(path: Path, model: str) -> tuple[list[Chunk], str, int]:
    corpus_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    chunks: list[Chunk] = []
    rejected = 0
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("needs_review") or record.get("review_status") != "approved":
                rejected += 1
                continue
            chunk_id = str(record.get("chunk_id", "")).strip()
            text = str(record.get("embedding_text", "")).strip()
            if not chunk_id or not text:
                raise ValueError(f"Invalid chunk at line {line_number}: missing chunk_id/embedding_text")
            if chunk_id in seen:
                raise ValueError(f"Duplicate chunk_id at line {line_number}: {chunk_id}")
            seen.add(chunk_id)
            chunks.append(
                Chunk(chunk_id, text, scalar_metadata(record, model, corpus_sha256))
            )
    return chunks, corpus_sha256, rejected


def existing_ids(collection: Any, ids: list[str], lookup_size: int = 500) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(ids), lookup_size):
        result = collection.get(ids=ids[start : start + lookup_size], include=[])
        found.update(result.get("ids", []))
    return found


def is_quota_exhausted(error: RateLimitError) -> bool:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        detail = body.get("error", body)
        if isinstance(detail, dict) and detail.get("code") == "insufficient_quota":
            return True
    return "insufficient_quota" in str(error)


def embed_with_retry(
    client: OpenAI,
    model: str,
    texts: list[str],
    max_retries: int,
) -> tuple[list[list[float]], int]:
    for attempt in range(max_retries + 1):
        try:
            response = client.embeddings.create(model=model, input=texts)
            ordered = sorted(response.data, key=lambda item: item.index)
            return [item.embedding for item in ordered], response.usage.prompt_tokens
        except RateLimitError as error:
            if is_quota_exhausted(error):
                raise RuntimeError(
                    "OpenAI quota is exhausted. Add credit, then rerun this command to resume."
                ) from error
            if attempt == max_retries:
                raise
        except (APIConnectionError, APITimeoutError):
            if attempt == max_retries:
                raise
        delay = min(60.0, (2**attempt) + random.random())
        print(f"API tạm lỗi; thử lại sau {delay:.1f}s ({attempt + 1}/{max_retries})", flush=True)
        time.sleep(delay)
    raise AssertionError("retry loop ended unexpectedly")


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--persist-dir", type=Path, default=DEFAULT_DB)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if not 1 <= args.batch_size <= 256:
        raise SystemExit("--batch-size must be between 1 and 256")
    if not args.input.exists():
        raise SystemExit(f"Input does not exist: {args.input}")

    chunks, corpus_sha256, rejected = load_approved_chunks(args.input, args.model)
    print(f"Input: {args.input}")
    print(f"Approved chunks: {len(chunks)} | skipped review chunks: {rejected}")
    print(f"Model: {args.model} | collection: {args.collection}")
    print(f"Corpus SHA-256: {corpus_sha256}")
    if args.dry_run:
        print("Dry run hoàn tất; chưa gọi OpenAI và chưa ghi Chroma.")
        return 0

    load_dotenv(ROOT / ".env")
    try:
        import chromadb
    except ImportError as error:
        raise SystemExit("Missing chromadb. Run: pip install chromadb") from error

    client = OpenAI()
    chroma_client = chromadb.PersistentClient(path=str(args.persist_dir))
    collection = chroma_client.get_or_create_collection(
        name=args.collection,
        metadata={
            "embedding_model": args.model,
            "corpus_sha256": corpus_sha256,
            "hnsw:space": "cosine",
        },
    )
    metadata = collection.metadata or {}
    stored_model = metadata.get("embedding_model")
    if stored_model and stored_model != args.model:
        raise SystemExit(
            f"Collection uses {stored_model}, not {args.model}; choose a new collection name."
        )

    already_done = existing_ids(collection, [chunk.chunk_id for chunk in chunks])
    pending = [chunk for chunk in chunks if chunk.chunk_id not in already_done]
    print(f"Đã có: {len(already_done)} | còn lại: {len(pending)}", flush=True)

    completed = len(already_done)
    total_tokens = 0
    started_at = time.monotonic()
    state = {
        "status": "running",
        "model": args.model,
        "collection": args.collection,
        "corpus_sha256": corpus_sha256,
        "total_chunks": len(chunks),
        "completed_chunks": completed,
        "prompt_tokens_this_run": total_tokens,
        "updated_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
    }
    write_state(args.state_file, state)

    try:
        for batch_number, batch in enumerate(batched(pending, args.batch_size), start=1):
            vectors, prompt_tokens = embed_with_retry(
                client, args.model, [chunk.text for chunk in batch], args.max_retries
            )
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                embeddings=vectors,
                documents=[chunk.text for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )
            completed += len(batch)
            total_tokens += prompt_tokens
            elapsed = max(time.monotonic() - started_at, 0.001)
            rate = (completed - len(already_done)) / elapsed
            remaining = len(chunks) - completed
            eta = remaining / rate if rate else 0
            print(
                f"Batch {batch_number}: {completed}/{len(chunks)} "
                f"({completed / len(chunks):.1%}) | tokens={total_tokens} | ETA={eta:.0f}s",
                flush=True,
            )
            state.update(
                completed_chunks=completed,
                prompt_tokens_this_run=total_tokens,
                updated_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            )
            write_state(args.state_file, state)
    except (Exception, KeyboardInterrupt) as error:
        state.update(
            status="stopped",
            error=type(error).__name__,
            completed_chunks=completed,
            prompt_tokens_this_run=total_tokens,
            updated_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        )
        write_state(args.state_file, state)
        print(f"Dừng tại {completed}/{len(chunks)}: {error}", file=sys.stderr, flush=True)
        return 130 if isinstance(error, KeyboardInterrupt) else 1

    state.update(
        status="complete",
        completed_chunks=completed,
        prompt_tokens_this_run=total_tokens,
        updated_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
    )
    write_state(args.state_file, state)
    print(f"Hoàn tất: {completed}/{len(chunks)} chunks; tokens run này: {total_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
