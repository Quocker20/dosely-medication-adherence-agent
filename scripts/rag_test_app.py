from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.rag_retrieval import SafeDrugRAG  # noqa: E402
from src.rag_retrieval.conversation_store import (  # noqa: E402
    ConversationLimitError,
    ConversationStore,
)
from src.rag_retrieval.input_guardrail import contextual_drug_offset  # noqa: E402

app = FastAPI(title="RemindRx RAG Test UI")
logger = logging.getLogger("remindrx.rag_test")


def _configure_logging() -> None:
    """Make every test run visible, including under uvicorn."""
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


_configure_logging()


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)
    conversation_id: str | None = None


@lru_cache(maxsize=1)
def get_service() -> SafeDrugRAG:
    return SafeDrugRAG()


@lru_cache(maxsize=1)
def get_store() -> ConversationStore:
    return ConversationStore(ROOT / "data" / "rag_test_history.sqlite3")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "rag-test.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "index": "rag_dense_index", "model": "text-embedding-3-large"}


@app.post("/api/conversations")
async def create_conversation() -> dict:
    return get_store().create()


@app.get("/api/conversations")
async def list_conversations() -> list[dict]:
    return get_store().list()


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    try:
        return get_store().get(conversation_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> None:
    try:
        get_store().delete(conversation_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error


@app.post("/api/query")
async def query(request: QueryRequest) -> dict:
    test_id = uuid4().hex[:8]
    started_at = datetime.now(timezone.utc)  # noqa: UP017 -- project venv is Python 3.10
    started = time.perf_counter()
    conversation_id = request.conversation_id
    if conversation_id is None:
        conversation_id = get_store().create()["id"]
    try:
        conversation = get_store().get(conversation_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    if conversation["exchange_count"] >= conversation["max_exchanges"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cuộc trò chuyện đã đạt giới hạn {conversation['max_exchanges']} lượt.",
        )
    logger.info(
        "RAG_TEST_START id=%s conversation=%s top_k=%s question=%r",
        test_id, conversation_id, request.top_k, request.question,
    )
    # Build deterministic, ordered conversation memory from recognized drug
    # entities. Consecutive questions about the same medicine remain one topic.
    drug_topics: list[tuple[str, str]] = []
    for message in conversation["messages"]:
        if message["role"] != "user":
            continue
        inferred = get_service().rag.infer_drug(message["content"])
        if inferred[0] and (not drug_topics or drug_topics[-1][0] != inferred[0]):
            drug_topics.append(inferred)
    context_drug = None
    if drug_topics:
        offset = contextual_drug_offset(request.question)
        if abs(offset) <= len(drug_topics):
            context_drug = drug_topics[offset]
    try:
        result = await asyncio.to_thread(
            get_service().query,
            request.question,
            top_k=request.top_k,
            context_drug=context_drug,
        )
    except Exception:
        logger.exception(
            "RAG_TEST_ERROR id=%s elapsed_ms=%.1f",
            test_id, (time.perf_counter() - started) * 1000,
        )
        raise
    try:
        saved = get_store().append_exchange(
            conversation_id, request.question, result.answer, result.status
        )
    except ConversationLimitError as error:
        raise HTTPException(status_code=409, detail="Cuộc trò chuyện đã đạt giới hạn.") from error
    payload = result.to_dict()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    trace = {
        "test_id": test_id,
        "started_at": started_at.isoformat(),
        "elapsed_ms": elapsed_ms,
        "top_k": request.top_k,
        "status": result.status,
        "safety_reason": result.safety_reason,
        "grounding_valid": result.grounding_valid,
        "grounding_errors": result.grounding_errors,
        "retrieved_count": len(result.sources),
        "sources": [
            {
                "number": source.number,
                "chunk_id": source.chunk_id,
                "score": round(source.score, 6),
                "drug_name": source.drug_name,
                "section": source.section,
                "pages": f"{source.page_start}-{source.page_end}",
            }
            for source in result.sources
        ],
    }
    payload.update(
        conversation_id=conversation_id,
        exchange_count=saved["exchange_count"],
        max_exchanges=saved["max_exchanges"],
        trace=trace,
    )
    logger.info(
        "RAG_TEST_END id=%s status=%s elapsed_ms=%s grounding=%s sources=%s",
        test_id, result.status, elapsed_ms, result.grounding_valid,
        ",".join(f"{source.chunk_id}:{source.score:.6f}" for source in result.sources) or "none",
    )
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
