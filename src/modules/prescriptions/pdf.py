"""Prescription PDF export — pure rendering, no DB, no I/O, no wall-clock
reads. Layout follows Phụ lục I of Thông tư 26/2025/TT-BYT; see
docs/prescription-pdf-export-plan.md for the field-by-field mapping and the
seeding rules this module must not violate (never seed a strength/
concentration value; every seeded field must look obviously synthetic; the
watermark is what keeps the sheet from passing as a real prescription).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_FONT_REGULAR = _FONT_DIR / "NotoSans-Regular.ttf"
_FONT_BOLD = _FONT_DIR / "NotoSans-Bold.ttf"

_FALLBACK_TIMEZONE = "Asia/Ho_Chi_Minh"

_SEX_LABELS: dict[str, str] = {
    "MALE": "Nam",
    "FEMALE": "Nữ",
    "OTHER": "Khác",
}

_MEAL_RELATION_LABELS: dict[str | None, str] = {
    "BEFORE_MEAL": "Trước ăn",
    "AFTER_MEAL": "Sau ăn",
    "WITH_MEAL": "Trong bữa ăn",
    None: "",
}

_ROUTE_LABELS: dict[str, str] = {
    "ORAL": "Uống",
    "INJECTION": "Tiêm",
    "TOPICAL": "Bôi ngoài da",
}

_UNSET = "(chưa cập nhật)"
_UNBOUNDED = "(dùng liên tục)"
_UNDETERMINED = "(không xác định)"
_UNKNOWN_DOCTOR = "(không xác định)"
_STRENGTH_PLACEHOLDER = "(theo nhãn thuốc)"

_DOSE_SLOTS: tuple[tuple[str, str], ...] = (
    ("morning", "Sáng"),
    ("noon", "Trưa"),
    ("evening", "Chiều"),
    ("bedtime", "Tối"),
)


@dataclass(frozen=True)
class PdfPatient:
    name: str
    dob: date | None
    sex: str | None
    phone: str
    timezone: str
    emergency_note: str | None


@dataclass(frozen=True)
class PdfDoctor:
    name: str
    license_no: str
    specialty: str | None


@dataclass(frozen=True)
class PdfItem:
    display_name: str
    composition: str | None
    dose_unit: str
    morning: Decimal | None
    noon: Decimal | None
    evening: Decimal | None
    bedtime: Decimal | None
    route: str
    meal_relation: str | None
    start_date: date
    end_date: date | None
    instructions: str | None
    is_critical: bool


@dataclass(frozen=True)
class PrescriptionPdfData:
    prescription_id: uuid.UUID
    approved_at: datetime
    diagnosis_note: str | None
    patient: PdfPatient
    doctor: PdfDoctor | None
    items: tuple[PdfItem, ...]


@dataclass(frozen=True)
class PdfSeeds:
    clinic_name: str
    clinic_address: str
    clinic_phone: str
    clinic_code: str
    patient_id_number: str
    patient_address: str
    patient_insurance_no: str
    patient_weight: str
    followup_note: str
    max_free_text_chars: int


def _resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_FALLBACK_TIMEZONE)


def _display_name(name: str) -> str:
    # "NULL" is the literal placeholder _resolve_or_create_patient writes for
    # NOT NULL columns with no default — never surface it verbatim.
    stripped = name.strip()
    if not stripped or stripped.upper() == "NULL":
        return _UNSET
    return stripped


def _format_dob(dob: date | None) -> tuple[str, str]:
    """Returns (dob_label, age_label). Age is in months for a patient under
    72 months old (TT 26/2025 requirement for young children), else years."""
    if dob is None:
        return _UNSET, ""
    today = date.today()
    months = (today.year - dob.year) * 12 + (today.month - dob.month)
    if today.day < dob.day:
        months -= 1
    months = max(months, 0)
    dob_label = dob.strftime("%d/%m/%Y")
    if months < 72:
        return dob_label, f"{months} tháng tuổi"
    years = months // 12
    return dob_label, f"{years} tuổi"


def _format_sex(sex: str | None) -> str:
    if sex is None:
        return _UNSET
    return _SEX_LABELS.get(sex.upper(), sex)


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "–"
    try:
        normalized = value.normalize()
    except InvalidOperation:
        return "–"
    if normalized == 0:
        return "–"
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _format_quantity(item: PdfItem) -> str:
    if item.end_date is None:
        return _UNBOUNDED
    if item.end_date < item.start_date:
        return _UNDETERMINED
    days = (item.end_date - item.start_date).days + 1
    total = Decimal(0)
    for slot, _ in _DOSE_SLOTS:
        dose = getattr(item, slot)
        if dose is not None:
            total += dose
    if total == 0:
        return "–"
    total_qty = total * days
    return f"{_format_decimal(total_qty)} {item.dose_unit}"


def _format_duration(item: PdfItem) -> str:
    start = item.start_date.strftime("%d/%m/%Y")
    if item.end_date is None:
        return f"{start} - {_UNBOUNDED}"
    if item.end_date < item.start_date:
        return _UNDETERMINED
    end = item.end_date.strftime("%d/%m/%Y")
    days = (item.end_date - item.start_date).days + 1
    return f"{start} - {end} ({days} ngày)"


def _truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 1].rstrip() + "…"


class _PrescriptionPdf(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.add_font("NotoSans", "", str(_FONT_REGULAR))
        self.add_font("NotoSans", "B", str(_FONT_BOLD))
        self.set_margins(15, 15, 15)

    def header(self) -> None:
        # fpdf2 calls header() on every add_page() — explicit and, via
        # set_auto_page_break, implicit ones triggered mid-render. The
        # watermark must land on every page a long item list spills onto,
        # not just the first — an unwatermarked page is exactly what the
        # watermark exists to prevent (docs/prescription-pdf-export-plan.md
        # §5 seeding safety rule 2).
        self.set_font("NotoSans", "B", 34)
        self.set_text_color(230, 230, 230)
        page_center_x = self.w / 2
        page_center_y = self.h / 2
        with self.rotation(35, page_center_x, page_center_y):
            self.set_xy(page_center_x - 90, page_center_y - 10)
            self.cell(180, 20, "MÔ PHỎNG — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ", align="C")
        self.set_text_color(0, 0, 0)
        # cell() above leaves the cursor at page-center Y (YPos.TOP default);
        # add_page() already positioned it at the top margin before calling
        # header(), so restore that for whatever body content follows.
        self.set_xy(self.l_margin, self.t_margin)


def render_prescription_pdf(data: PrescriptionPdfData, seeds: PdfSeeds) -> bytes:
    pdf = _PrescriptionPdf()
    pdf.add_page()

    tz = _resolve_timezone(data.patient.timezone)
    approved_local = data.approved_at.astimezone(tz)

    # --- Clinic header ---
    pdf.set_font("NotoSans", "B", 13)
    pdf.cell(0, 7, seeds.clinic_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("NotoSans", "", 9)
    pdf.cell(
        0, 5,
        f"{seeds.clinic_address}  ·  ĐT: {seeds.clinic_phone}  ·  Mã CSKCB: {seeds.clinic_code}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(2)
    pdf.set_draw_color(150, 150, 150)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # --- Title ---
    pdf.set_font("NotoSans", "B", 16)
    pdf.cell(0, 8, "ĐƠN THUỐC", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("NotoSans", "", 9)
    pdf.cell(
        0, 5, f"Số: {data.prescription_id.hex[:8]}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C",
    )
    pdf.ln(3)

    # --- Patient block ---
    dob_label, age_label = _format_dob(data.patient.dob)
    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(35, 6, "Họ tên:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    name_line = _display_name(data.patient.name)
    pdf.cell(95, 6, name_line, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(28, 6, "Ngày sinh:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    dob_text = dob_label if not age_label else f"{dob_label}  ({age_label})"
    pdf.cell(0, 6, dob_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(35, 6, "Giới tính:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(95, 6, _format_sex(data.patient.sex), new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(28, 6, "Cân nặng:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(0, 6, seeds.patient_weight, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(35, 6, "Số định danh:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(95, 6, seeds.patient_id_number, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(28, 6, "Số thẻ BHYT:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(0, 6, seeds.patient_insurance_no, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(35, 6, "Địa chỉ:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(0, 6, seeds.patient_address, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(35, 6, "Điện thoại:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    pdf.cell(0, 6, data.patient.phone, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if data.patient.emergency_note:
        pdf.set_font("NotoSans", "B", 10)
        pdf.cell(35, 6, "Lưu ý / tiền sử:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("NotoSans", "", 10)
        pdf.multi_cell(
            0, 6,
            _truncate(data.patient.emergency_note, seeds.max_free_text_chars),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )

    pdf.ln(2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # --- Diagnosis ---
    pdf.set_font("NotoSans", "B", 10)
    pdf.cell(28, 6, "Chẩn đoán:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("NotoSans", "", 10)
    diagnosis = _truncate(data.diagnosis_note, seeds.max_free_text_chars) or _UNSET
    pdf.multi_cell(0, 6, diagnosis, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # --- Items ---
    has_critical = False
    for index, item in enumerate(data.items, start=1):
        if item.is_critical:
            has_critical = True
        pdf.set_font("NotoSans", "B", 10)
        marker = " [!]" if item.is_critical else ""
        composition = item.composition or ""
        name_text = item.display_name
        if composition:
            name_text = f"{name_text} ({composition})"
        header = f"{index:02d}. {name_text}{marker}"
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(140, 6, header, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("NotoSans", "", 9)
        pdf.set_x(pdf.w - pdf.r_margin - 45)
        pdf.multi_cell(45, 6, _STRENGTH_PLACEHOLDER, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

        pdf.set_font("NotoSans", "", 9)
        route_label = _ROUTE_LABELS.get(item.route, item.route)
        meal_label = _MEAL_RELATION_LABELS.get(item.meal_relation, item.meal_relation or "")
        line2 = f"      SL: {_format_quantity(item)} · {route_label}"
        if meal_label:
            line2 += f" · {meal_label}"
        pdf.cell(0, 5, line2, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        dose_parts = [
            f"{label} {_format_decimal(getattr(item, slot))}"
            for slot, label in _DOSE_SLOTS
        ]
        pdf.cell(
            0, 5, "      " + " · ".join(dose_parts) + f" ({item.dose_unit})",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.cell(0, 5, f"      {_format_duration(item)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if item.instructions:
            pdf.set_font("NotoSans", "", 9)
            note = _truncate(item.instructions, seeds.max_free_text_chars)
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, 5, f"Ghi chú: {note}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    if has_critical:
        pdf.set_font("NotoSans", "", 8)
        pdf.set_text_color(150, 0, 0)
        pdf.cell(
            0, 5, "[!]  Thuốc cần đặc biệt lưu ý do bác sĩ đánh dấu.",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_text_color(0, 0, 0)

    pdf.ln(2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # --- Footer: instructions, validity, signature ---
    pdf.set_font("NotoSans", "", 9)
    pdf.multi_cell(0, 5, f"Lời dặn: {seeds.followup_note}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(
        0, 5,
        "Đơn có giá trị mua, lĩnh thuốc trong 30 ngày kể từ ngày kê.",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(4)

    signature_x = pdf.w - pdf.r_margin - 70
    pdf.set_xy(signature_x, pdf.get_y())
    pdf.set_font("NotoSans", "", 9)
    pdf.cell(70, 5, f"Ngày {approved_local.strftime('%d')} tháng {approved_local.strftime('%m')} năm {approved_local.strftime('%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_x(signature_x)
    pdf.set_font("NotoSans", "B", 9)
    pdf.cell(70, 5, "BÁC SĨ KÊ ĐƠN", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_x(signature_x)
    pdf.set_font("NotoSans", "", 8)
    pdf.cell(70, 5, "(Ký điện tử — bản mô phỏng)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(10)
    pdf.set_x(signature_x)
    pdf.set_font("NotoSans", "B", 9)
    if data.doctor is None:
        pdf.cell(70, 5, _UNKNOWN_DOCTOR, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    else:
        pdf.cell(70, 5, f"BS. {data.doctor.name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_x(signature_x)
        pdf.set_font("NotoSans", "", 8)
        specialty = f" · {data.doctor.specialty}" if data.doctor.specialty else ""
        pdf.cell(
            70, 5, f"CCHN: {data.doctor.license_no}{specialty}",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C",
        )

    pdf.ln(6)
    pdf.set_font("NotoSans", "", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 4,
        "Bản mô phỏng phục vụ học thuật — không có giá trị pháp lý.",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C",
    )
    pdf.set_text_color(0, 0, 0)

    output = pdf.output()
    return bytes(output)
