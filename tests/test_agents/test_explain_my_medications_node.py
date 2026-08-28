from unittest.mock import AsyncMock

import pytest

from src.agents.nodes import explain_my_medications_node as module


def _medication(name: str, medication_id: str) -> dict:
    return {
        "medication_id": medication_id,
        "display_name": name,
        "dose_unit": "viên",
        "morning_dose": 1,
        "noon_dose": None,
        "evening_dose": None,
        "bedtime_dose": None,
        "meal_relation": "AFTER_MEAL",
        "instructions": None,
    }


@pytest.mark.asyncio
async def test_explains_each_authenticated_medication_in_one_contiguous_block(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(
            return_value={
                "as_of": "2026-08-27",
                "medications": [
                    _medication("Amlodipin 5mg", "med-1"),
                    _medication("Metformin 500mg", "med-2"),
                ],
            }
        ),
    )
    calls = []

    def fake_explain(name: str):
        calls.append(name)
        return "ANSWERED", f"Thông tin riêng của {name}."

    monkeypatch.setattr(module, "_explain_one", fake_explain)

    result = await module.explain_my_medications_node({})
    answer = result["messages"][0].content

    assert calls == ["Amlodipin 5mg", "Metformin 500mg"]
    assert answer.index("1. Amlodipin 5mg") < answer.index("2. Metformin 500mg")
    assert "Theo đơn của bạn" in answer
    # Citations are hidden in the user-facing composition layer.
    assert "[Nguồn" not in answer
    module.get.assert_awaited_once_with("/patients/me/medications/current")


def test_citations_are_removed_from_user_facing_text():
    cleaned = module._without_citations(
        "- Uống sau bữa ăn [Nguồn 1].\n- Không nhai viên thuốc [Nguồn 2]."
    )
    assert cleaned == "Uống sau bữa ăn. Không nhai viên thuốc."


@pytest.mark.asyncio
async def test_empty_active_prescription_does_not_call_rag(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(return_value={"as_of": "2026-08-27", "medications": []}),
    )
    explain = AsyncMock()
    monkeypatch.setattr(module, "_explain_one", explain)

    result = await module.explain_my_medications_node({})

    assert "không có đơn thuốc đã duyệt còn hiệu lực" in result["messages"][0].content
    explain.assert_not_called()


def test_unresolved_drug_never_calls_rag_query(monkeypatch):
    class FakeRagCore:
        @staticmethod
        def infer_drug(_name):
            return None, None

    class FakeSafeRag:
        rag = FakeRagCore()
        query = AsyncMock()

    monkeypatch.setattr(module, "_get_rag_service", lambda: FakeSafeRag())

    status, message = module._explain_one("Tên thuốc không xác định 123")

    assert status == "NO_DATA"
    assert "khớp chính xác" in message
    FakeSafeRag.query.assert_not_called()
