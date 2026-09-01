import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.nodes.grounding_validator_node import (
    _SAFE_FALLBACK,
    grounding_validator_node,
    validate_grounded_answer,
)

SOURCES = {
    1: (
        "[Nguồn 1] ACID AMINOSALICYLIC — Tương tác thuốc, trang 136\n"
        "Diphenhydramin làm giảm hấp thu PAS, do đó tránh dùng đồng thời."
    )
}


def test_valid_cited_answer_passes():
    result = validate_grounded_answer("Diphenhydramin làm giảm hấp thu PAS [Nguồn 1].", SOURCES)
    assert result.valid is True


@pytest.mark.parametrize(
    ("answer", "expected_error"),
    [
        ("Diphenhydramin làm giảm hấp thu PAS.", "missing_citation"),
        ("Diphenhydramin làm giảm hấp thu PAS [Nguồn 9].", "unknown_citation:9"),
        ("PAS phải dùng liều 500 mg [Nguồn 1].", "unsupported_number:500 mg"),
        ("Warfarin chữa khỏi hoàn toàn bệnh lao [Nguồn 1].", "low_grounding"),
    ],
)
def test_invalid_grounding_is_detected(answer: str, expected_error: str):
    result = validate_grounded_answer(answer, SOURCES)
    assert result.valid is False
    assert any(expected_error in error for error in result.errors)


@pytest.mark.asyncio
async def test_node_replaces_ungrounded_rag_answer():
    state = {
        "messages": [
            HumanMessage(content="PAS tương tác thế nào?"),
            AIMessage(
                content="",
                tool_calls=[{"name": "search_drug_formulary", "args": {"query": "PAS"}, "id": "1"}],
            ),
            ToolMessage(content=SOURCES[1], tool_call_id="1", name="search_drug_formulary"),
            AIMessage(content="PAS chữa khỏi mọi bệnh."),
        ]
    }
    result = await grounding_validator_node(state)
    assert result["grounding_valid"] is False
    assert result["messages"][0].content == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_node_does_not_require_citation_when_rag_was_not_used():
    result = await grounding_validator_node(
        {"messages": [HumanMessage(content="Xin chào"), AIMessage(content="Xin chào bạn!")]}
    )
    assert result == {"grounding_valid": True, "grounding_errors": []}


def test_validator_accepts_cited_numbered_interaction_list() -> None:
    answer = (
        "Zolpidem có các tương tác đáng chú ý như sau:\n"
        "1. Rượu: Có thể làm tăng tác dụng an thần [Nguồn 1].\n"
        "2. Rifampicin: Phối hợp làm giảm tác dụng zolpidem [Nguồn 1]."
    )
    sources = {1: "[Nguồn 1] Rượu làm tăng tác dụng an thần. Rifampicin phối hợp làm giảm tác dụng zolpidem."}
    result = validate_grounded_answer(answer, sources)
    assert result.valid is True


def test_validator_does_not_split_st_john_or_block_general_interaction() -> None:
    answer = (
        "Zolpidem có một số tương tác thuốc quan trọng. "
        "Cỏ St. John làm giảm tác dụng zolpidem [Nguồn 1]. "
        "Thuốc có thể tăng tác dụng nhưng không cần hiệu chỉnh liều khi phối hợp "
        "[Nguồn 1]."
    )
    sources = {
        1: "[Nguồn 1] Cỏ St. John làm giảm tác dụng zolpidem. Thuốc có thể "
        "tăng tác dụng nhưng không cần hiệu chỉnh liều khi phối hợp."
    }
    assert validate_grounded_answer(answer, sources).valid is True


def test_validator_blocks_personal_treatment_decision() -> None:
    answer = "Bạn có thể phối hợp hai thuốc này [Nguồn 1]."
    sources = {1: "[Nguồn 1] Hai thuốc có thông tin tương tác."}
    result = validate_grounded_answer(answer, sources)
    assert result.valid is False
    assert "unsafe_treatment_decision" in result.errors


def test_validator_blocks_direct_paracetamol_advice_after_alcohol() -> None:
    result = validate_grounded_answer(
        "Bạn có thể uống paracetamol sau khi uống bia [Nguồn 1].",
        {1: "Uống nhiều rượu có thể làm tăng độc tính với gan của paracetamol."},
    )
    assert result.valid is False
    assert "unsafe_treatment_decision" in result.errors


def test_validator_does_not_treat_children_as_first_person() -> None:
    result = validate_grounded_answer(
        "Trẻ em có thể dùng paracetamol theo đường uống [Nguồn 1].",
        {1: "Trẻ em có thể dùng paracetamol theo đường uống."},
    )
    assert "unsafe_treatment_decision" not in result.errors


def test_validator_does_not_treat_children_in_coadministration_as_first_person() -> None:
    result = validate_grounded_answer(
        "Trẻ em có thể dùng cùng hai thuốc này [Nguồn 1].",
        {1: "Trẻ em có thể dùng cùng hai thuốc này."},
    )
    assert result.valid is True, result.errors


def test_validator_does_not_treat_rash_as_second_person() -> None:
    result = validate_grounded_answer(
        "Ban đỏ có thể tăng khi phối hợp hai thuốc [Nguồn 1].",
        {1: "Ban đỏ có thể tăng khi phối hợp hai thuốc."},
    )
    assert result.valid is True, result.errors


@pytest.mark.parametrize(
    "answer",
    [
        "Không nên tự ý phối hợp Warfarin hay Aspirin vì có thể làm tăng nguy cơ chảy máu [Nguồn 1].",
        "Không nên tự ý phối hợp Warfarin hoặc Aspirin vì có thể làm tăng nguy cơ chảy máu [Nguồn 1].",
        "Dùng đồng thời Warfarin với Aspirin có thể làm tăng nguy cơ chảy máu [Nguồn 1].",
        "Phối hợp Warfarin và Aspirin có thể làm tăng nguy cơ chảy máu [Nguồn 1].",
        "Aspirin có thể làm tăng tác dụng chống đông của Warfarin [Nguồn 1].",
        "Warfarin hay Aspirin đều có thể liên quan đến nguy cơ chảy máu khi phối hợp [Nguồn 1].",
        "Bệnh nhân dùng đồng thời Warfarin và Aspirin có thể tăng nguy cơ chảy máu [Nguồn 1].",
    ],
)
def test_validator_allows_objective_drug_interaction_answers(answer: str) -> None:
    sources = {
        1: (
            "[Nguồn 1] Warfarin và Aspirin có tương tác. Không nên tự ý phối hợp "
            "Warfarin hoặc Aspirin vì có thể làm tăng nguy cơ chảy máu. Dùng đồng "
            "thời Warfarin với Aspirin có thể làm tăng nguy cơ chảy máu. Aspirin "
            "có thể làm tăng tác dụng chống đông của Warfarin. Bệnh nhân dùng đồng "
            "thời hai thuốc có thể tăng nguy cơ chảy máu."
        )
    }
    result = validate_grounded_answer(answer, sources)
    assert result.valid is True, result.errors
