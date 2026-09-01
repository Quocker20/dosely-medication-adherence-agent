from src.agents.prescription_consistency import validate_prescription_schedule


def _item(**overrides):
    item = {
        "id": "item-1",
        "medication_id": "med-1",
        "display_name": "Metformin 500mg",
        "dose_unit": "viên",
        "route": "ORAL",
        "morning_dose": "1.000",
        "noon_dose": None,
        "evening_dose": None,
        "bedtime_dose": None,
        "meal_relation": "AFTER_MEAL",
    }
    item.update(overrides)
    return item


def _dose(**overrides):
    dose = {
        "prescription_item_id": "item-1",
        "medication_id": "med-1",
        "medication_name": "Metformin 500mg",
        "dose_slot": "MORNING",
        "dose_value": "1",
        "dose_unit": "viên",
        "meal_relation": "AFTER_MEAL",
    }
    dose.update(overrides)
    return dose


def test_matching_prescription_and_schedule_are_safe():
    assert validate_prescription_schedule([_item()], [_dose()]) == []


def test_wrong_dose_unit_and_meal_relation_are_all_reported():
    issues = validate_prescription_schedule(
        [_item()], [_dose(dose_value="2", dose_unit="ml", meal_relation="BEFORE_MEAL")]
    )
    assert any("liều trong lịch không khớp" in issue for issue in issues)
    assert any("đơn vị liều" in issue for issue in issues)
    assert any("bữa ăn" in issue for issue in issues)


def test_schedule_row_from_inactive_item_is_rejected():
    issues = validate_prescription_schedule([_item()], [_dose(prescription_item_id="other-item")])
    assert any("không thuộc đơn còn hiệu lực" in issue for issue in issues)


def test_missing_route_or_prescribed_slot_is_rejected():
    issues = validate_prescription_schedule([_item(route=None)], [])
    assert any("chưa ghi đường dùng" in issue for issue in issues)
    assert any("thiếu cữ morning" in issue for issue in issues)


def test_duplicate_active_medication_is_rejected():
    issues = validate_prescription_schedule(
        [_item(), _item(id="item-2")],
        [_dose(), _dose(prescription_item_id="item-2")],
    )
    assert any("xuất hiện nhiều lần" in issue for issue in issues)
