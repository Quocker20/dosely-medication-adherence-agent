from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tools.drug_info_tools import _NO_MATCH_MESSAGE, search_drug_info
from src.modules.planning.core.backend_client import BackendAPIError


def _medication(**overrides):
    med = {
        "id": "med-1",
        "name": "Paracetamol 500mg",
        "composition": "Paracetamol 500mg",
        "manufacturer": "XYZ Pharma",
        "uses": "Giảm đau, hạ sốt",
        "side_effects": "Buồn nôn",
        "source_name": "DrugBank",
        "is_active": True,
    }
    med.update(overrides)
    return med


@pytest.mark.asyncio
async def test_short_query_returns_canned_message_without_calling_backend():
    with patch("src.agents.tools.drug_info_tools.get", new=AsyncMock()) as mock_get:
        result = await search_drug_info.ainvoke({"query": "a"})

    assert result == _NO_MATCH_MESSAGE
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_no_match_returns_canned_message():
    with patch(
        "src.agents.tools.drug_info_tools.get",
        new=AsyncMock(return_value={"content": []}),
    ):
        result = await search_drug_info.ainvoke({"query": "thuốc lạ không tồn tại"})

    assert result == _NO_MATCH_MESSAGE


@pytest.mark.asyncio
async def test_backend_error_falls_back_to_canned_message():
    with patch(
        "src.agents.tools.drug_info_tools.get",
        new=AsyncMock(side_effect=BackendAPIError(503, "down")),
    ):
        result = await search_drug_info.ainvoke({"query": "paracetamol"})

    assert result == _NO_MATCH_MESSAGE


@pytest.mark.asyncio
async def test_match_formats_result_with_citation():
    with patch(
        "src.agents.tools.drug_info_tools.get",
        new=AsyncMock(return_value={"content": [_medication()]}),
    ) as mock_get:
        result = await search_drug_info.ainvoke({"query": "paracetamol"})

    assert "Paracetamol 500mg" in result
    assert "medication_id: med-1" in result
    assert "DrugBank" in result
    assert "Giảm đau, hạ sốt" in result
    kwargs = mock_get.call_args.kwargs
    assert kwargs["params"]["search"] == "paracetamol"


@pytest.mark.asyncio
async def test_caps_results_at_three():
    content = [_medication(id=f"med-{i}", name=f"Drug {i}") for i in range(5)]
    with patch(
        "src.agents.tools.drug_info_tools.get",
        new=AsyncMock(return_value={"content": content}),
    ):
        result = await search_drug_info.ainvoke({"query": "drug"})

    assert result.count("medication_id:") == 3
