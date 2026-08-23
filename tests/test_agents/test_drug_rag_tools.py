from unittest.mock import patch

import pytest

from src.agents.tools.drug_rag_tools import _NO_MATCH, search_drug_formulary
from src.rag_retrieval import RetrievalHit


class FakeRAG:
    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, query: str, top_k: int):
        assert query == "Acid ascorbic có chỉ định gì?"
        assert top_k == 5
        return self.hits


@pytest.mark.asyncio
async def test_formulary_tool_returns_grounded_source():
    hit = RetrievalHit(
        chunk_id="chunk-1",
        document="Thuốc: ACID ASCORBIC\nMục: Chỉ định\nĐiều trị thiếu vitamin C.",
        metadata={
            "drug_name": "ACID ASCORBIC",
            "section_label": "Chỉ định",
            "page_start": 100,
            "page_end": 100,
        },
        score=1.0,
    )
    with patch("src.agents.tools.drug_rag_tools._get_rag", return_value=FakeRAG([hit])):
        result = await search_drug_formulary.ainvoke(
            {"query": "Acid ascorbic có chỉ định gì?"}
        )
    assert "[Nguồn 1]" in result
    assert "trang 100" in result
    assert "chunk-1" in result
    assert "<du_lieu_duoc_thu>" in result


@pytest.mark.asyncio
async def test_formulary_tool_has_safe_no_match_response():
    with patch("src.agents.tools.drug_rag_tools._get_rag", return_value=FakeRAG([])):
        result = await search_drug_formulary.ainvoke(
            {"query": "Acid ascorbic có chỉ định gì?"}
        )
    assert result == _NO_MATCH
