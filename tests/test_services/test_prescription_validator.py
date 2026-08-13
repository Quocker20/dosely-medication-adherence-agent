from src.modules.planning.core.clinical import (
    Prescription,
    PrescriptionItem,
    PrescriptionItemIn,
    PrescriptionStatus,
    Timing,
)
from src.modules.planning.core.prescription_validator import (
    assert_clinical_fields_unchanged,
    validate_items,
)


def _item(**overrides) -> PrescriptionItemIn:
    base = {
        "drug_name": "Amlodipin 5mg",
        "dose_per_intake": "1 viên",
        "frequency_per_day": 1,
        "timing": Timing.AFTER_BREAKFAST,
        "treatment_days": 30,
    }
    base.update(overrides)
    return PrescriptionItemIn(**base)


def test_valid_prescription_passes():
    report = validate_items([_item()])
    assert report.ok
    assert report.issues == []


def test_empty_prescription_rejected():
    report = validate_items([])
    assert not report.ok
    assert report.issues[0].code == "EMPTY_PRESCRIPTION"


def test_missing_drug_name_and_dose():
    report = validate_items([_item(drug_name="  ", dose_per_intake="")])
    codes = {issue.code for issue in report.issues}
    assert codes == {"MISSING_DRUG_NAME", "MISSING_DOSE"}


def test_frequency_out_of_range():
    report = validate_items([_item(frequency_per_day=6)])
    assert not report.ok
    assert [i.code for i in report.issues] == ["FREQUENCY_OUT_OF_RANGE"]


def test_duration_out_of_range():
    report = validate_items([_item(treatment_days=400)])
    assert [i.code for i in report.issues] == ["DURATION_OUT_OF_RANGE"]


def test_duplicate_drug_detected_case_insensitively():
    report = validate_items([_item(), _item(drug_name="amlodipin 5mg")])
    assert [i.code for i in report.issues] == ["DUPLICATE_DRUG"]


def _approved_prescription() -> Prescription:
    return Prescription(
        id="RX-1",
        patient_id="p-01",
        doctor_id="dr-1",
        status=PrescriptionStatus.APPROVED,
        created_at="2026-08-06T00:00:00+00:00",
        items=[PrescriptionItem(seq=1, **_item().model_dump())],
    )


def test_agent_output_matching_prescription_is_accepted():
    assert assert_clinical_fields_unchanged(_approved_prescription(), [_item()]) == []


def test_agent_cannot_change_dose():
    issues = assert_clinical_fields_unchanged(_approved_prescription(), [_item(dose_per_intake="2 viên")])
    assert [i.code for i in issues] == ["AGENT_MUTATED_CLINICAL_FIELD"]
    assert issues[0].field == "dose_per_intake"


def test_agent_cannot_change_frequency_or_duration():
    issues = assert_clinical_fields_unchanged(
        _approved_prescription(),
        [_item(frequency_per_day=3, treatment_days=90)],
    )
    assert {i.field for i in issues} == {"frequency_per_day", "treatment_days"}


def test_agent_cannot_introduce_new_drug():
    issues = assert_clinical_fields_unchanged(_approved_prescription(), [_item(drug_name="Losartan 50mg")])
    assert [i.code for i in issues] == ["UNKNOWN_DRUG_IN_AGENT_OUTPUT"]
