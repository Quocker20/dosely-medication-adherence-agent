"""Process-wide shared DrugRAG / SafeDrugRAG instances (P-09).

Every chatbot node and tool used to build its own lru_cache'd instance, so the
Chroma/dense index and the lexical tables were loaded several times. All of
them now go through this module, and the app lifespan warms the single shared
instance at startup (fail-soft).
"""

from __future__ import annotations

import logging
import threading

from src.rag_retrieval.safe_service import SafeDrugRAG
from src.rag_retrieval.service import DrugRAG, index_available

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_rag: DrugRAG | None = None
_safe_rag: SafeDrugRAG | None = None


def get_drug_rag() -> DrugRAG:
    """The one shared DrugRAG. Construction failures are not cached."""
    global _rag
    if _rag is None:
        with _lock:
            if _rag is None:
                _rag = DrugRAG()
    return _rag


def get_safe_drug_rag() -> SafeDrugRAG:
    """SafeDrugRAG wrapping the shared DrugRAG (same underlying index)."""
    global _safe_rag
    if _safe_rag is None:
        rag = get_drug_rag()
        with _lock:
            if _safe_rag is None:
                _safe_rag = SafeDrugRAG(rag)
    return _safe_rag


def warm_up_rag() -> bool:
    """Load the shared index and lexical tables. Never raises.

    A missing or broken index only logs a warning: the app (and the test
    suite) must still start, and the first request that needs RAG reports the
    problem through the existing unavailable-reply path.
    """
    try:
        if not index_available():
            logger.warning("RAG warm-up skipped: no drug index found under data/")
            return False
        get_safe_drug_rag()
        get_drug_rag().warm_up()
    except Exception:  # noqa: BLE001 — warm-up is best effort
        logger.warning("RAG warm-up failed; continuing without a warm index", exc_info=True)
        return False
    logger.info("RAG index warmed up")
    return True


def reset_shared_rag() -> None:
    """Drop the shared instances (tests only)."""
    global _rag, _safe_rag
    with _lock:
        _rag = None
        _safe_rag = None
