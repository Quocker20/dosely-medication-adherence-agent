"""Deterministic RAG branch for formulary questions in patient chat."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.state import AgentState
from src.rag_retrieval import SafeDrugRAG

_UNAVAILABLE_REPLY = (
    "Mình chưa thể tra cứu Dược thư Quốc gia lúc này. Bạn vui lòng hỏi bác sĩ hoặc dược sĩ trước khi thay đổi điều trị."
)


@lru_cache(maxsize=1)
def _get_rag_service() -> SafeDrugRAG:
    """Reuse the loaded index and client across chat turns."""
    return SafeDrugRAG()


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def drug_rag_node(state: AgentState) -> dict:
    """Answer a drug-information turn through the guarded RAG service only.

    This route intentionally bypasses the general chat LLM.  It prevents a
    model from deciding that it can answer a formulary question without first
    retrieving approved source material.
    """
    try:
        result = await asyncio.to_thread(_get_rag_service().query, _last_human_text(state))
    except Exception:  # noqa: BLE001 - retrieval/generation failure must fail safely
        return {
            "messages": [AIMessage(content=_UNAVAILABLE_REPLY)],
            "grounding_valid": False,
            "grounding_errors": ["rag_unavailable"],
        }
    return {
        "messages": [AIMessage(content=result.answer)],
        "grounding_valid": result.grounding_valid,
        "grounding_errors": result.grounding_errors,
    }
