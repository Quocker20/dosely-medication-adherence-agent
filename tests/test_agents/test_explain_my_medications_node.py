from unittest.mock import AsyncMock

import pytest

from src.agents.nodes import explain_my_medications_node as module


def _medication(name: str, medication_id: str) -> dict:
    return {
        "id": f"item-{medication_id}",
        "medication_id": medication_id,
        "display_name": name,
        "dose_unit": "viên",
        "morning_dose": 1,
        "noon_dose": None,
        "evening_dose": None,
        "bedtime_dose": None,
        "meal_relation": "AFTER_MEAL",
        "route": "ORAL",
        "instructions": None,
    }


@pytest.mark.asyncio
async def test_explains_each_authenticated_medication_in_one_contiguous_block(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(
            side_effect=[
                {
                    "as_of": "2026-08-27",
                    "medications": [
                        _medication("Amlodipin 5mg", "med-1"),
                        _medication("Metformin 500mg", "med-2"),
                    ],
                },
                {
                    "date": "2026-08-27",
                    "doses": [
                        {
                            "prescription_item_id": "item-med-1",
                            "medication_name": "Amlodipin 5mg",
                            "dose_slot": "MORNING",
                            "dose_value": 1,
                            "dose_unit": "viên",
                            "meal_relation": "AFTER_MEAL",
                        },
                        {
                            "prescription_item_id": "item-med-2",
                            "medication_name": "Metformin 500mg",
                            "dose_slot": "MORNING",
                            "dose_value": 1,
                            "dose_unit": "viên",
                            "meal_relation": "AFTER_MEAL",
                        },
                    ],
                },
            ]
        ),
    )
    calls = []

    def fake_explain(name: str):
        calls.append(name)
        return "ANSWERED", f"Thông tin riêng của {name}."

    monkeypatch.setattr(module, "_explain_one", fake_explain)

    result = await module.explain_my_medications_node({"patient_id": "patient-1"})
    answer = result["messages"][0].content

    assert calls == ["Amlodipin 5mg", "Metformin 500mg"]
    assert answer.index("1. Amlodipin 5mg") < answer.index("2. Metformin 500mg")
    assert "Chỉ dẫn cá nhân từ đơn đã duyệt" in answer
    assert "Sau bữa ăn" in answer
    assert "AFTER_MEAL" not in answer
    # Citations are hidden in the user-facing composition layer.
    assert "[Nguồn" not in answer
    assert module.get.await_args_list[0].args == ("/patients/me/medications/current",)
    assert module.get.await_args_list[1].args == ("/patients/patient-1/schedules",)


def test_citations_are_removed_from_user_facing_text():
    cleaned = module._without_citations("- Uống sau bữa ăn [Nguồn 1].\n- Không nhai viên thuốc [Nguồn 2].")
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


def test_regimen_never_invents_missing_instructions_or_formats_one_as_thousand():
    text = module._regimen(
        {
            "morning_dose": "1.000",
            "dose_unit": "viên",
            "meal_relation": None,
            "instructions": None,
        }
    )
    assert "Sáng: 1 viên" in text
    assert "1.000 viên" not in text
    assert "Liên quan bữa ăn: Đơn chưa ghi" in text
    assert "Dặn dò bổ sung: Đơn chưa ghi" in text
    assert "Đường dùng: Đơn chưa ghi" in text


def test_regimen_displays_prescribed_route_and_minimum_interval():
    text = module._regimen(
        {
            "morning_dose": "1",
            "dose_unit": "viên",
            "route": "ORAL",
            "meal_relation": "WITH_MEAL",
            "instructions": "Nuốt nguyên viên",
            "minimum_interval_minutes": 360,
        }
    )
    assert "Đường dùng: Đường uống" in text
    assert "Dùng cùng bữa ăn" in text
    assert "Khoảng cách tối thiểu theo đơn: 360 phút" in text


@pytest.mark.asyncio
async def test_device_date_is_used_to_select_active_prescription(monkeypatch):
    get = AsyncMock(return_value={"as_of": "2026-08-30", "medications": []})
    monkeypatch.setattr(module, "get", get)
    result = await module.explain_my_medications_node({"client_date": "2026-08-30"})
    get.assert_awaited_once_with("/patients/me/medications/current", params={"as_of": "2026-08-30"})
    assert "không có đơn thuốc" in result["messages"][0].content


@pytest.mark.asyncio
async def test_schedule_conflict_stops_before_rag(monkeypatch):
    medication = _medication("Metformin 500mg", "med-1")
    get = AsyncMock(
        side_effect=[
            {"as_of": "2026-08-30", "medications": [medication]},
            {
                "date": "2026-08-30",
                "doses": [
                    {
                        "prescription_item_id": "item-med-1",
                        "medication_name": "Metformin 500mg",
                        "dose_slot": "MORNING",
                        "dose_value": 1000,
                        "dose_unit": "viên",
                        "meal_relation": "AFTER_MEAL",
                    }
                ],
            },
        ]
    )
    explain = AsyncMock()
    monkeypatch.setattr(module, "get", get)
    monkeypatch.setattr(module, "_explain_one", explain)

    result = await module.explain_my_medications_node({"patient_id": "patient-1", "client_date": "2026-08-30"})

    assert "liều trong lịch không khớp liều trong đơn" in result["messages"][0].content
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
