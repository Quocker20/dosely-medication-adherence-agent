from pathlib import Path

import pytest

from src.rag_retrieval.conversation_store import (
    MAX_EXCHANGES,
    ConversationLimitError,
    ConversationStore,
)


def test_conversation_persists_and_auto_titles(tmp_path: Path):
    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation = store.create()
    saved = store.append_exchange(
        conversation["id"], "Abacavir có chống chỉ định gì?", "Câu trả lời", "answered"
    )
    assert saved["exchange_count"] == 1
    assert saved["title"] == "Abacavir có chống chỉ định gì?"
    assert [message["role"] for message in saved["messages"]] == ["user", "assistant"]
    assert store.list()[0]["exchange_count"] == 1


def test_conversation_enforces_exchange_limit(tmp_path: Path):
    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation_id = store.create()["id"]
    for index in range(MAX_EXCHANGES):
        store.append_exchange(conversation_id, f"Question {index}", "Answer", "answered")
    with pytest.raises(ConversationLimitError):
        store.append_exchange(conversation_id, "One too many", "Answer", "answered")
    saved = store.get(conversation_id)
    assert saved["exchange_count"] == MAX_EXCHANGES
    assert len(saved["messages"]) == MAX_EXCHANGES * 2


def test_unknown_conversation_raises_key_error(tmp_path: Path):
    store = ConversationStore(tmp_path / "history.sqlite3")
    with pytest.raises(KeyError):
        store.get("missing")


def test_delete_removes_conversation_and_messages(tmp_path: Path):
    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation_id = store.create()["id"]
    store.append_exchange(conversation_id, "Question", "Answer", "answered")
    store.delete(conversation_id)
    with pytest.raises(KeyError):
        store.get(conversation_id)
