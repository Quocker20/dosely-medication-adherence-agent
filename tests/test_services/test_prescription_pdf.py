"""Pure-renderer tests for src.modules.prescriptions.pdf — no DB, no I/O.

Covers the dirty-data table from docs/prescription-pdf-export-plan.md §6
Step 4: every column here is nullable, FK-less, or otherwise unconstrained
at the schema level, so the renderer must degrade to a placeholder instead
of crashing or printing something misleading (a literal "NULL", a negative
day count, an un-decoded glyph).
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from pypdf import PdfReader
import io

from src.modules.prescriptions.pdf import (
    PdfDoctor,
    PdfItem,
    PdfPatient,
    PdfSeeds,
    PrescriptionPdfData,
    _display_name,
    _format_decimal,
    _format_dob,
    _format_duration,
    _format_quantity,
    _format_sex,
    _resolve_timezone,
    _truncate,
    render_prescription_pdf,
)


def _seeds(**overrides) -> PdfSeeds:
    defaults = dict(
        clinic_name="PHÒNG KHÁM MÔ PHỎNG",
        clinic_address="Địa chỉ mô phỏng",
        clinic_phone="1900 0000",
        clinic_code="SIM-00000",
        patient_id_number="000000000000",
        patient_address="Địa chỉ mô phỏng",
        patient_insurance_no="SIM0000000000000",
        patient_weight="60 kg",
        followup_note="Tái khám theo lịch hẹn.",
        max_free_text_chars=2000,
    )
    defaults.update(overrides)
    return PdfSeeds(**defaults)


def _item(**overrides) -> PdfItem:
    defaults = dict(
        display_name="Paracetamol 500",
        composition="Paracetamol",
        dose_unit="viên",
        morning=Decimal("1"),
        noon=None,
        evening=Decimal("1"),
        bedtime=None,
        route="ORAL",
        meal_relation="AFTER_MEAL",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        instructions="Uống nhiều nước",
        is_critical=False,
    )
    defaults.update(overrides)
    return PdfItem(**defaults)


def _data(**overrides) -> PrescriptionPdfData:
    defaults = dict(
        prescription_id=uuid.uuid4(),
        approved_at=datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc),
        diagnosis_note="Viêm họng cấp",
        patient=PdfPatient(
            name="Nguyễn Văn Ánh", dob=date(1958, 3, 12), sex="MALE",
            phone="0912345678", timezone="Asia/Ho_Chi_Minh", emergency_note=None,
        ),
        doctor=PdfDoctor(name="Trần Thị Bích", license_no="001234/HN-CCHN", specialty="Nội khoa"),
        items=(_item(),),
    )
    defaults.update(overrides)
    return PrescriptionPdfData(**defaults)


def _pages_text(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [p.extract_text() for p in reader.pages]


# ---------------------------------------------------------------------------
# Helper functions — the dirty-data table
# ---------------------------------------------------------------------------


class TestDisplayName:
    def test_null_placeholder_never_prints_literal_null(self):
        """_resolve_or_create_patient writes literal 'NULL' into name for
        NOT NULL columns with no default; must never reach the PDF as-is."""
        assert _display_name("NULL") == "(chưa cập nhật)"
        assert _display_name("null") == "(chưa cập nhật)"

    def test_blank_falls_back_to_placeholder(self):
        assert _display_name("   ") == "(chưa cập nhật)"

    def test_real_name_passes_through(self):
        assert _display_name("Nguyễn Văn A") == "Nguyễn Văn A"


class TestFormatDob:
    def test_none_dob_is_placeholder_with_no_age(self):
        assert _format_dob(None) == ("(chưa cập nhật)", "")

    def test_under_72_months_reports_months_not_years(self):
        """TT 26/2025/TT-BYT requires months, not years, under 72 months."""
        young = date.today().replace(year=date.today().year - 2)
        _, age = _format_dob(young)
        assert "tháng tuổi" in age

    def test_adult_reports_years(self):
        _, age = _format_dob(date(1958, 3, 12))
        assert "tuổi" in age and "tháng" not in age


class TestFormatSex:
    def test_none_is_placeholder(self):
        assert _format_sex(None) == "(chưa cập nhật)"

    def test_known_codes_map_to_vietnamese(self):
        assert _format_sex("MALE") == "Nam"
        assert _format_sex("FEMALE") == "Nữ"
        assert _format_sex("OTHER") == "Khác"

    def test_unknown_value_falls_through_without_crashing(self):
        """sex is a free-text String(20) column with no CHECK constraint —
        an unrecognized value must render as-is, never raise KeyError."""
        assert _format_sex("WEIRD_VALUE") == "WEIRD_VALUE"


class TestFormatDecimal:
    def test_none_and_zero_both_render_dash(self):
        assert _format_decimal(None) == "–"
        assert _format_decimal(Decimal("0")) == "–"

    def test_trailing_zeros_stripped(self):
        assert _format_decimal(Decimal("1.000")) == "1"

    def test_uses_vietnamese_decimal_comma(self):
        assert _format_decimal(Decimal("0.500")) == "0,5"


class TestQuantityAndDuration:
    def test_open_ended_prescription_renders_unbounded(self):
        item = _item(end_date=None)
        assert _format_quantity(item) == "(dùng liên tục)"
        assert "(dùng liên tục)" in _format_duration(item)

    def test_end_before_start_never_produces_negative_count(self):
        """No CHECK constraint enforces end_date >= start_date at the DB
        layer; the renderer must guard this itself."""
        item = _item(start_date=date(2026, 9, 10), end_date=date(2026, 9, 1))
        assert _format_quantity(item) == "(không xác định)"
        assert _format_duration(item) == "(không xác định)"

    def test_quantity_sums_only_populated_dose_slots_times_days(self):
        item = _item(
            morning=Decimal("1"), noon=None, evening=Decimal("1"), bedtime=None,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 5),
        )
        assert _format_quantity(item) == "10 viên"  # (1+1) * 5 days


class TestTruncate:
    def test_none_and_empty_render_empty_string(self):
        assert _truncate(None, 100) == ""
        assert _truncate("", 100) == ""

    def test_long_text_truncated_with_ellipsis(self):
        text = "A" * 5000
        result = _truncate(text, 2000)
        assert len(result) == 2000
        assert result.endswith("…")

    def test_short_text_passes_through_unchanged(self):
        assert _truncate("short", 2000) == "short"


class TestResolveTimezone:
    def test_valid_timezone_used_as_is(self):
        assert str(_resolve_timezone("Asia/Ho_Chi_Minh")) == "Asia/Ho_Chi_Minh"

    def test_invalid_timezone_falls_back(self):
        """patient_profiles.timezone is a free-text String(50) with no
        validation against the IANA database."""
        assert str(_resolve_timezone("Not/A_Real_Zone")) == "Asia/Ho_Chi_Minh"


# ---------------------------------------------------------------------------
# Full render — end to end
# ---------------------------------------------------------------------------


class TestRenderPrescriptionPdf:
    def test_happy_path_produces_valid_single_page_pdf(self):
        pdf_bytes = render_prescription_pdf(_data(), _seeds())
        assert pdf_bytes[:5] == b"%PDF-"
        pages = _pages_text(pdf_bytes)
        assert len(pages) == 1
        assert "Nguyễn Văn Ánh" in pages[0]
        assert "Trần Thị Bích" in pages[0]
        assert "Paracetamol 500" in pages[0]

    def test_worst_case_dirty_data_does_not_raise(self):
        """Every field here is either null, a stale placeholder, or an
        out-of-catalog reference — the combination a real row can actually
        contain, per the dirty-data table."""
        data = _data(
            diagnosis_note=None,
            patient=PdfPatient(
                name="NULL", dob=None, sex="UNKNOWN_CODE", phone="0912345678",
                timezone="Bogus/Zone", emergency_note="x" * 5000,
            ),
            doctor=None,  # doctor_id was ON DELETE SET NULL
            items=(
                _item(
                    composition=None,  # medication_id has no FK, row may be deleted
                    morning=Decimal("1.000"), noon=Decimal("0"),
                    evening=Decimal("1"), bedtime=None,
                    instructions="y" * 5000,
                    is_critical=True,
                ),
            ),
        )
        pdf_bytes = render_prescription_pdf(data, _seeds())
        assert pdf_bytes[:5] == b"%PDF-"
        text = "".join(_pages_text(pdf_bytes))
        assert "(chưa cập nhật)" in text  # NULL name placeholder
        assert "NULL" not in text.replace("(chưa cập nhật)", "")  # never printed raw

    def test_no_glyph_missing_from_embedded_font(self, capfd):
        """Regression: → and ⚠ are absent from the embedded Noto Sans TTF;
        fpdf2 warns on stderr and silently drops them instead of raising.
        A prior version of this renderer used both."""
        data = _data(items=(_item(is_critical=True, end_date=None),))
        render_prescription_pdf(data, _seeds())
        captured = capfd.readouterr()
        assert "missing the following glyphs" not in captured.err

    def test_watermark_present_on_every_page_including_overflow(self):
        """Regression: header() must draw the watermark on every page — a
        prior version drew it once after add_page(), so an item list long
        enough to overflow onto page 2+ shipped an unwatermarked page,
        exactly what the watermark exists to prevent (plan §5 rule 2)."""
        many_items = tuple(
            _item(
                display_name=f"Thuốc số {i}",
                instructions="Hướng dẫn sử dụng chi tiết, uống đều đặn mỗi ngày.",
            )
            for i in range(24)
        )
        pdf_bytes = render_prescription_pdf(_data(items=many_items), _seeds())
        pages = _pages_text(pdf_bytes)
        assert len(pages) > 1, "expected this item count to overflow onto multiple pages"
        for i, text in enumerate(pages, start=1):
            assert "MÔ PHỎNG" in text and "KHÔNG CÓ GIÁ TRỊ PHÁP LÝ" in text, (
                f"page {i} is missing the watermark"
            )

    def test_does_not_seed_a_strength_value(self):
        """The one field seeding must never fabricate — see plan §5 rule 4."""
        pdf_bytes = render_prescription_pdf(_data(), _seeds())
        text = _pages_text(pdf_bytes)[0]
        assert "(theo nhãn thuốc)" in text

    def test_utc_approval_converts_to_patient_local_calendar_day(self):
        """A late-UTC approval must not print the wrong calendar day once
        converted to the patient's timezone."""
        data = _data(
            approved_at=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),  # 03:00 next day in VN
            patient=PdfPatient(
                name="Nguyễn Văn Ánh", dob=None, sex=None, phone="0912345678",
                timezone="Asia/Ho_Chi_Minh", emergency_note=None,
            ),
        )
        text = _pages_text(render_prescription_pdf(data, _seeds()))[0]
        assert "Ngày 02 tháng 09 năm 2026" in text
