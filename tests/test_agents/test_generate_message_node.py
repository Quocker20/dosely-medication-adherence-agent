from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.nodes.generate_message_node import generate_message_node

DOSE = {
    "drug": "Metformin 500mg",
    "time": "06:30",
    "meal_relation": "before_meal",
    "date": "2026-08-13",
}


def _mock_llm(content: str):
    mock = AsyncMock(return_value=AIMessage(content=content))
    patcher = patch("src.agents.nodes.generate_message_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.ainvoke = mock
    return patcher


@pytest.mark.asyncio
async def test_template_slot_filled_by_code_not_llm():
    patcher = _mock_llm("Chúc bạn một ngày tốt lành!")
    try:
        result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    assert "Metformin 500mg" in result["message"]
    assert "06:30" in result["message"]
    assert "trước bữa ăn" in result["message"]
    assert result["drug"] == "Metformin 500mg"
    assert result["time"] == "06:30"


@pytest.mark.asyncio
async def test_meal_relation_phrasing():
    cases = {
        "before_meal": "trước bữa ăn",
        "after_meal": "sau bữa ăn",
        "bedtime": "trước khi ngủ",
        None: None,
    }
    for relation, expected_phrase in cases.items():
        dose = {**DOSE, "meal_relation": relation}
        patcher = _mock_llm("Cố lên nhé!")
        try:
            result = await generate_message_node(dose)
        finally:
            patcher.stop()
        if expected_phrase:
            assert expected_phrase in result["message"]
        else:
            assert "," not in result["message"].split("lúc")[0]


@pytest.mark.asyncio
async def test_safe_encouragement_is_kept():
    patcher = _mock_llm("Hôm nay bạn thật tuyệt vời, cố lên nhé!")
    try:
        result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    assert "Hôm nay bạn thật tuyệt vời, cố lên nhé!" in result["message"]


@pytest.mark.asyncio
async def test_encouragement_with_digit_falls_back_to_default():
    patcher = _mock_llm("Nhớ uống đủ 2 lần nhé!")  # chứa số -> phải bị chặn
    try:
        result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    assert "2 lần" not in result["message"]


@pytest.mark.asyncio
async def test_encouragement_with_drug_name_falls_back_to_default():
    patcher = _mock_llm("Metformin sẽ giúp bạn khỏe hơn!")  # lỡ nhắc tên thuốc
    try:
        result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    # Chỉ có 1 chỗ chứa "Metformin" là phần template, không phải câu động viên
    assert result["message"].lower().count("metformin") == 1


@pytest.mark.asyncio
async def test_llm_timeout_falls_back_to_default_and_never_raises():
    import asyncio

    patcher = patch("src.agents.nodes.generate_message_node.get_llm")
    mock_get_llm = patcher.start()

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(10)

    mock_get_llm.return_value.ainvoke = _hang
    try:
        with patch("src.agents.nodes.generate_message_node._LLM_TIMEOUT_SECONDS", 0.05):
            result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    assert "Metformin 500mg" in result["message"]
    assert result["message"].strip().endswith((".", "!"))


@pytest.mark.asyncio
async def test_llm_exception_falls_back_to_default():
    patcher = patch("src.agents.nodes.generate_message_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    try:
        result = await generate_message_node(DOSE)
    finally:
        patcher.stop()

    assert "Metformin 500mg" in result["message"]


def test_default_encouragement_is_deterministic():
    from src.agents.nodes.generate_message_node import _default_encouragement

    assert _default_encouragement("Metformin 500mg") == _default_encouragement("Metformin 500mg")
