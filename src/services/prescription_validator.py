"""Validator đơn thuốc — cổng cuối cùng trước khi persist thay đổi lâm sàng.

Chạy hoàn toàn bằng code xác định. Agent KHÔNG được bypass hàm này, và cũng
không được gọi nó với dữ liệu do agent tự sinh (mục 7.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.config import get_settings
from src.models.clinical import (
    Prescription,
    PrescriptionItemIn,
    ValidationIssue,
    ValidationReport,
)


def validate_items(items: Sequence[PrescriptionItemIn]) -> ValidationReport:
    """Kiểm tra đơn trước khi bác sĩ duyệt.

    Ngưỡng lấy từ Settings để không hardcode luật lâm sàng rải rác trong code.
    """
    settings = get_settings()
    issues: list[ValidationIssue] = []

    if not items:
        issues.append(
            ValidationIssue(
                code="EMPTY_PRESCRIPTION",
                field="items",
                message="Đơn phải có ít nhất 1 thuốc.",
            )
        )

    for index, item in enumerate(items):
        seq = index + 1
        label = f"Thuốc {seq}"

        if not item.drug_name.strip():
            issues.append(
                ValidationIssue(
                    code="MISSING_DRUG_NAME",
                    field="drug_name",
                    item_seq=seq,
                    message=f"{label}: chưa nhập tên thuốc.",
                )
            )
        if not item.dose_per_intake.strip():
            issues.append(
                ValidationIssue(
                    code="MISSING_DOSE",
                    field="dose_per_intake",
                    item_seq=seq,
                    message=f"{label}: chưa nhập liều mỗi lần.",
                )
            )
        if not 1 <= item.frequency_per_day <= settings.max_frequency_per_day:
            issues.append(
                ValidationIssue(
                    code="FREQUENCY_OUT_OF_RANGE",
                    field="frequency_per_day",
                    item_seq=seq,
                    message=(
                        f"{label}: số lần/ngày phải trong khoảng 1–{settings.max_frequency_per_day}. "
                        "Ngoài khoảng này cần bác sĩ xác nhận bằng đơn riêng."
                    ),
                )
            )
        if not 1 <= item.treatment_days <= settings.max_treatment_days:
            issues.append(
                ValidationIssue(
                    code="DURATION_OUT_OF_RANGE",
                    field="treatment_days",
                    item_seq=seq,
                    message=f"{label}: số ngày điều trị phải trong khoảng 1–{settings.max_treatment_days}.",
                )
            )

    seen: dict[str, int] = {}
    for index, item in enumerate(items):
        key = item.drug_name.strip().lower()
        if not key:
            continue
        if key in seen:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_DRUG",
                    field="drug_name",
                    item_seq=index + 1,
                    message=(
                        f'Thuốc "{item.drug_name.strip()}" bị nhập trùng '
                        f"(dòng {seen[key]} và {index + 1}) — gộp lại thành một dòng."
                    ),
                )
            )
        else:
            seen[key] = index + 1

    return ValidationReport(ok=not issues, issues=issues)


def assert_clinical_fields_unchanged(
    prescription: Prescription,
    candidate_items: Sequence[PrescriptionItemIn],
) -> list[ValidationIssue]:
    """So khớp dữ liệu agent trả về với đơn đã duyệt.

    Agent chỉ được tính giờ. Nếu bất kỳ trường lâm sàng nào lệch so với đơn gốc
    thì output bị từ chối — đây là chốt chặn cho "AI không tự đổi liều".
    """
    issues: list[ValidationIssue] = []
    source = {item.drug_name.strip().lower(): item for item in prescription.items}

    for candidate in candidate_items:
        key = candidate.drug_name.strip().lower()
        origin = source.get(key)
        if origin is None:
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_DRUG_IN_AGENT_OUTPUT",
                    field="drug_name",
                    message=f'Agent trả về thuốc "{candidate.drug_name}" không có trong đơn đã duyệt.',
                )
            )
            continue

        for field, origin_value, candidate_value in (
            ("dose_per_intake", origin.dose_per_intake, candidate.dose_per_intake),
            ("frequency_per_day", origin.frequency_per_day, candidate.frequency_per_day),
            ("treatment_days", origin.treatment_days, candidate.treatment_days),
        ):
            if origin_value != candidate_value:
                issues.append(
                    ValidationIssue(
                        code="AGENT_MUTATED_CLINICAL_FIELD",
                        field=field,
                        item_seq=origin.seq,
                        message=(
                            f"{origin.drug_name}: agent đổi {field} từ {origin_value!r} sang "
                            f"{candidate_value!r} — bị từ chối, agent chỉ được tính giờ."
                        ),
                    )
                )

    return issues
