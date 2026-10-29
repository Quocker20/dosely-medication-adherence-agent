"""P-09: one shared DrugRAG, precomputed folded names, fail-soft warm-up."""
import logging

import pytest

from src.rag_retrieval import provider
from src.rag_retrieval.service import DrugRAG, fold


class _Collection:
    def __init__(self):
        self.get_calls = 0

    def get(self, include=None):
        self.get_calls += 1
        return {
            "ids": ["1", "2"],
            "documents": ["a", "b"],
            "metadatas": [
                {"normalized_drug_name": "paracetamol", "drug_name": "PARACETAMOL"},
                {"normalized_drug_name": "amoxicilin", "drug_name": "AMOXICILIN"},
            ],
        }


@pytest.fixture(autouse=True)
def _reset():
    provider.reset_shared_rag()
    yield
    provider.reset_shared_rag()


def test_provider_returns_same_instance(monkeypatch):
    built = []

    def fake_init(self, **kwargs):
        built.append(self)

    monkeypatch.setattr(DrugRAG, "__init__", fake_init)
    a = provider.get_drug_rag()
    assert provider.get_drug_rag() is a
    s1 = provider.get_safe_drug_rag()
    assert provider.get_safe_drug_rag() is s1
    assert s1.rag is a
    assert len(built) == 1


def test_all_chatbot_modules_share_one_instance(monkeypatch):
    monkeypatch.setattr(DrugRAG, "__init__", lambda self, **kw: None)
    from src.chatbot.nodes import drug_rag_node, explain_my_medications_node, scheduled_drug_info_node, scope_guard_node
    from src.chatbot.tools import drug_rag_tools

    base = provider.get_drug_rag()
    assert drug_rag_node._get_rag_service().rag is base
    assert explain_my_medications_node._get_rag_service().rag is base
    assert scheduled_drug_info_node._rag().rag is base
    assert scheduled_drug_info_node._identity_rag() is base
    assert scope_guard_node._drug_resolver() is base
    assert drug_rag_tools._get_rag() is base


def test_warm_up_with_missing_index_does_not_raise(monkeypatch, caplog):
    monkeypatch.setattr(provider, "index_available", lambda: False)
    with caplog.at_level(logging.WARNING):
        assert provider.warm_up_rag() is False
    assert "warm-up" in caplog.text


def test_warm_up_with_broken_index_does_not_raise(monkeypatch, caplog):
    monkeypatch.setattr(provider, "index_available", lambda: True)

    def boom():
        raise RuntimeError("corrupt index")

    monkeypatch.setattr(provider, "get_safe_drug_rag", boom)
    with caplog.at_level(logging.WARNING):
        assert provider.warm_up_rag() is False
    assert "warm-up failed" in caplog.text


def test_warm_up_loads_lexical_index_once(monkeypatch):
    collection = _Collection()
    rag = DrugRAG(collection=collection, client=object())
    monkeypatch.setattr(provider, "index_available", lambda: True)
    provider._rag = rag
    assert provider.warm_up_rag() is True
    assert collection.get_calls == 1
    rag.infer_drug("paracetamol uống thế nào")
    assert collection.get_calls == 1


def test_folded_names_computed_once(monkeypatch):
    rag = DrugRAG(collection=_Collection(), client=object())
    calls = []
    import src.rag_retrieval.service as svc

    real = svc.fold
    monkeypatch.setattr(svc, "fold", lambda v: (calls.append(v), real(v))[1])
    rag.warm_up()
    after_load = len(calls)
    assert {f for _, _, f in rag._folded_drug_names} == {"paracetamol", "amoxicilin"}
    for _ in range(3):
        assert rag.infer_drug("paracetamol có tác dụng phụ gì")[0] == "paracetamol"
    # Per query: the query is folded; the headings are not re-folded.
    assert len(calls) - after_load <= 3 * 2
    assert fold("Đ") == "d"


def test_shared_rag_infers_drug_without_api_key(monkeypatch):
    """Name inference must not need OPENAI_API_KEY; only embed/generate do."""
    import src.rag_retrieval.service as svc
    from src.core.config import get_settings

    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    def _boom(**_kw):
        raise RuntimeError("OpenAI client built eagerly")

    monkeypatch.setattr(svc, "OpenAI", _boom)
    try:
        monkeypatch.setattr(provider, "DrugRAG", lambda: DrugRAG(collection=_Collection()))
        rag = provider.get_drug_rag()
        assert rag is provider.get_drug_rag()
        assert rag.infer_drug("Paracetamol")[0] == "paracetamol"
        with pytest.raises(RuntimeError):
            _ = rag.client  # only embedding/generation touch the client
    finally:
        get_settings.cache_clear()
