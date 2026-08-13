"""
Bộ test cho tầng 1 — Constraint solver tính lịch uống thuốc.

Test theo HỢP ĐỒNG NGHIỆP VỤ, không phụ thuộc cách implement.
Nếu solver của bạn có signature khác, chỉ cần sửa hàm `solve()` ở phần
ADAPTER bên dưới — toàn bộ test còn lại giữ nguyên.

Chạy:
    pytest test_scheduler.py -v
    pytest test_scheduler.py -v -k "conflict"     # chỉ nhóm xung đột
"""

from datetime import time, datetime, timedelta

import pytest

# ============================================================ ADAPTER
# Sửa phần này cho khớp code thật của bạn.

from src.agents.nodes.compute_schedule import compute_schedule


def solve(prescription: dict, routine: dict, date: str = "2026-08-15") -> list[dict]:
    """Trả về list các liều đã xếp lịch.

    Mỗi phần tử tối thiểu phải có:
        {"drug": str, "time": "HH:MM", "meal_relation": str|None}
    """
    return compute_schedule(
        prescription=prescription,
        patient_routine=routine,
        target_date=date,
    )


# ============================================================ FIXTURES


@pytest.fixture
def routine():
    """Lịch sinh hoạt chuẩn dùng cho hầu hết test."""
    return {
        "wake_time": "06:00",
        "breakfast_time": "07:00",
        "lunch_time": "11:30",
        "dinner_time": "18:00",
        "bed_time": "21:30",
        "timezone": "Asia/Ho_Chi_Minh",
    }


@pytest.fixture
def routine_night_shift():
    """Bệnh nhân làm ca đêm — lịch sinh hoạt đảo ngược."""
    return {
        "wake_time": "14:00",
        "breakfast_time": "15:00",
        "lunch_time": "20:00",
        "dinner_time": "02:00",
        "bed_time": "06:00",
        "timezone": "Asia/Ho_Chi_Minh",
    }


def rx(*items) -> dict:
    """Helper tạo đơn thuốc nhanh."""
    return {"prescription_id": "test-rx", "items": list(items)}


def item(drug, freq, meal=None, interval=None, fixed=None) -> dict:
    d = {
        "drug_name": drug,
        "frequency_per_day": freq,
        "meal_relation": meal,
    }
    if interval:
        d["minimum_interval_minutes"] = interval
    if fixed:
        d["fixed_time_of_day"] = fixed
    return d


# ============================================================ HELPERS


def to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def times_of(doses, drug=None) -> list[int]:
    """Trả về danh sách thời điểm (phút từ 00:00), đã sắp xếp."""
    sel = [d for d in doses if drug is None or d["drug"] == drug]
    return sorted(to_minutes(d["time"]) for d in sel)


def in_sleep_window(minute: int, routine: dict) -> bool:
    bed = to_minutes(routine["bed_time"])
    wake = to_minutes(routine["wake_time"])
    if bed < wake:                      # ngủ không qua nửa đêm
        return bed <= minute < wake
    return minute >= bed or minute < wake


# ============================================================ 1. CƠ BẢN


class TestBasicFrequency:
    """Số liều sinh ra phải đúng với frequency."""

    @pytest.mark.parametrize("freq", [1, 2, 3, 4])
    def test_dose_count_matches_frequency(self, routine, freq):
        doses = solve(rx(item("Metformin", freq)), routine)
        assert len(doses) == freq

    def test_multiple_drugs_total_count(self, routine):
        doses = solve(rx(
            item("Metformin", 3),
            item("Amlodipine", 1),
            item("Rosuvastatin", 1),
        ), routine)
        assert len(doses) == 5
        assert len(times_of(doses, "Metformin")) == 3

    def test_no_duplicate_time_same_drug(self, routine):
        doses = solve(rx(item("Metformin", 3)), routine)
        t = times_of(doses, "Metformin")
        assert len(t) == len(set(t)), "Cùng 1 thuốc không được trùng giờ"


# ============================================================ 2. BỮA ĂN


class TestMealRelation:
    """Thuốc trước ăn / sau ăn phải bám đúng giờ bữa."""

    def test_before_meal_is_before(self, routine):
        doses = solve(rx(item("Metformin", 3, meal="before_meal")), routine)
        meals = [to_minutes(routine[k]) for k in
                 ("breakfast_time", "lunch_time", "dinner_time")]
        for d in doses:
            t = to_minutes(d["time"])
            nearest = min(meals, key=lambda m: abs(m - t))
            assert t < nearest, f"{d['time']} phải trước bữa {nearest//60}h"

    def test_before_meal_within_60min(self, routine):
        """Trước ăn nhưng không được quá sớm — 15-60 phút là hợp lý."""
        doses = solve(rx(item("Metformin", 3, meal="before_meal")), routine)
        meals = [to_minutes(routine[k]) for k in
                 ("breakfast_time", "lunch_time", "dinner_time")]
        for d in doses:
            t = to_minutes(d["time"])
            gap = min(m - t for m in meals if m > t)
            assert 10 <= gap <= 60, f"Khoảng cách tới bữa ăn bất thường: {gap} phút"

    def test_after_meal_is_after(self, routine):
        doses = solve(rx(item("Amlodipine", 1, meal="after_meal")), routine)
        meals = [to_minutes(routine[k]) for k in
                 ("breakfast_time", "lunch_time", "dinner_time")]
        t = to_minutes(doses[0]["time"])
        assert any(m < t <= m + 60 for m in meals)

    def test_no_meal_relation_still_scheduled(self, routine):
        """Thuốc không ghi thời điểm vẫn phải có giờ hợp lý."""
        doses = solve(rx(item("Vitamin D", 1)), routine)
        assert len(doses) == 1
        assert not in_sleep_window(to_minutes(doses[0]["time"]), routine)


# ============================================================ 3. GIỜ NGỦ


class TestSleepWindow:
    """Không được nhắc khi bệnh nhân đang ngủ."""

    def test_no_dose_during_sleep(self, routine):
        doses = solve(rx(
            item("Metformin", 3),
            item("Amlodipine", 2),
            item("Furosemide", 2),
        ), routine)
        for d in doses:
            assert not in_sleep_window(to_minutes(d["time"]), routine), \
                f"{d['drug']} bị xếp lúc {d['time']} — đang ngủ"

    def test_bedtime_drug_before_sleep(self, routine):
        """Thuốc ghi 'trước khi ngủ' phải sát giờ ngủ, không phải giữa đêm."""
        doses = solve(rx(item("Rosuvastatin", 1, meal="bedtime")), routine)
        t = to_minutes(doses[0]["time"])
        bed = to_minutes(routine["bed_time"])
        assert bed - 90 <= t <= bed, "Thuốc trước ngủ phải trong 90 phút trước giờ ngủ"

    def test_night_shift_routine(self, routine_night_shift):
        """Bệnh nhân ca đêm: ngủ 06:00-14:00, không nhắc trong khoảng đó."""
        doses = solve(rx(item("Metformin", 3)), routine_night_shift)
        for d in doses:
            t = to_minutes(d["time"])
            assert not (6 * 60 <= t < 14 * 60), \
                f"Xếp lúc {d['time']} trong khi BN ca đêm đang ngủ"


# ============================================================ 4. KHOẢNG CÁCH


class TestMinimumInterval:
    """Ràng buộc quan trọng nhất về mặt an toàn."""

    def test_same_drug_spacing(self, routine):
        """Các cữ cùng thuốc phải cách nhau đủ xa."""
        doses = solve(rx(item("Metformin", 3, interval=240)), routine)
        t = times_of(doses, "Metformin")
        for a, b in zip(t, t[1:]):
            assert b - a >= 240, f"Hai cữ chỉ cách {b-a} phút, cần ≥ 240"

    def test_cross_drug_interval(self, routine):
        """Hai thuốc kỵ nhau — ví dụ Canxi và Rosuvastatin."""
        doses = solve(rx(
            item("Rosuvastatin", 1, meal="bedtime"),
            item("Canxi", 2, interval=120),
        ), routine)

        ros = times_of(doses, "Rosuvastatin")
        can = times_of(doses, "Canxi")
        for r in ros:
            for c in can:
                assert abs(r - c) >= 120, \
                    f"Rosuvastatin {r//60}:{r%60:02d} và Canxi " \
                    f"{c//60}:{c%60:02d} chỉ cách {abs(r-c)} phút"

    def test_four_doses_fit_waking_hours(self, routine):
        """4 cữ/ngày cách nhau ≥ 3h cần 9 tiếng — vẫn vừa khoảng thức."""
        doses = solve(rx(item("Antibiotic", 4, interval=180)), routine)
        t = times_of(doses)
        for a, b in zip(t, t[1:]):
            assert b - a >= 180


# ============================================================ 5. XUNG ĐỘT


class TestConflictHandling:
    """Trường hợp không thể thỏa hết ràng buộc — hành vi phải rõ ràng.

    Đây là nhóm test hay bị bỏ sót nhất, và cũng là nhóm mà ban giám khảo
    hay hỏi nhất."""

    def test_impossible_constraint_raises_or_flags(self, routine):
        """4 cữ × cách 6 giờ = 24 giờ, không thể nhét vào 15 tiếng thức."""
        try:
            doses = solve(rx(item("X", 4, interval=360)), routine)
        except Exception as e:
            assert "conflict" in str(e).lower() or "infeasible" in str(e).lower(), \
                "Exception phải nêu rõ lý do là xung đột ràng buộc"
            return

        # Nếu không raise thì phải đánh dấu rõ
        assert any(d.get("conflict") or d.get("relaxed") for d in doses), \
            "Không giải được thì phải raise hoặc gắn cờ conflict/relaxed"

    def test_relaxation_never_breaks_hard_constraint(self, routine):
        """Khi nới lỏng, KHÔNG được nới ràng buộc an toàn.

        Được phép: xếp lệch giờ ăn, phân bổ không đều.
        Không được phép: cho hai liều sát nhau dưới minimum_interval.
        """
        try:
            doses = solve(rx(item("X", 4, interval=300)), routine)
        except Exception:
            return  # raise cũng là hành vi đúng

        t = times_of(doses)
        for a, b in zip(t, t[1:]):
            assert b - a >= 300, \
                "Nới lỏng đã phá vỡ minimum_interval — đây là lỗi an toàn"

    def test_empty_prescription(self, routine):
        doses = solve(rx(), routine)
        assert doses == []

    def test_missing_routine_field(self):
        """Thiếu thông tin lịch sinh hoạt — phải báo lỗi rõ, không đoán bừa."""
        incomplete = {"wake_time": "06:00", "bed_time": "21:30"}
        with pytest.raises(Exception):
            solve(rx(item("Metformin", 3, meal="before_meal")), incomplete)


# ============================================================ 6. ĐƠN THỰC TẾ


class TestRealWorldPrescription:
    """Đơn thuốc thật của bệnh nhân tiểu đường + tăng huyết áp."""

    @pytest.fixture
    def real_rx(self):
        return rx(
            item("Metformin 500mg", 3, meal="before_meal", interval=240),
            item("Gliclazide 30mg", 1, meal="before_meal"),
            item("Amlodipine 5mg", 1, meal="after_meal"),
            item("Losartan 50mg", 1, meal="after_meal"),
            item("Rosuvastatin 10mg", 1, meal="bedtime"),
            item("Aspirin 81mg", 1, meal="after_meal"),
        )

    def test_all_constraints_hold(self, real_rx, routine):
        doses = solve(real_rx, routine)

        assert len(doses) == 8

        for d in doses:
            assert not in_sleep_window(to_minutes(d["time"]), routine)

        met = times_of(doses, "Metformin 500mg")
        for a, b in zip(met, met[1:]):
            assert b - a >= 240

    def test_output_shape(self, real_rx, routine):
        """Kiểm tra định dạng đầu ra — tầng 2 sẽ phụ thuộc vào cấu trúc này."""
        doses = solve(real_rx, routine)
        for d in doses:
            assert "drug" in d and "time" in d
            assert isinstance(d["time"], str)
            h, m = d["time"].split(":")
            assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59


# ============================================================ 7. XÁC ĐỊNH


class TestDeterminism:
    """Cùng input phải luôn ra cùng output.

    Đây là lý do chính vì sao tầng này không dùng LLM."""

    def test_same_input_same_output(self, routine):
        p = rx(item("Metformin", 3, meal="before_meal"),
               item("Amlodipine", 1, meal="after_meal"))

        runs = [solve(p, routine) for _ in range(5)]
        first = sorted((d["drug"], d["time"]) for d in runs[0])
        for r in runs[1:]:
            assert sorted((d["drug"], d["time"]) for d in r) == first

    def test_item_order_does_not_matter(self, routine):
        """Đảo thứ tự thuốc trong đơn không được đổi kết quả."""
        a = item("Metformin", 3, meal="before_meal")
        b = item("Amlodipine", 1, meal="after_meal")

        r1 = solve(rx(a, b), routine)
        r2 = solve(rx(b, a), routine)

        assert sorted((d["drug"], d["time"]) for d in r1) == \
               sorted((d["drug"], d["time"]) for d in r2)


# ============================================================ 8. TIMEZONE


class TestTimezone:
    def test_timezone_preserved(self, routine):
        """Giờ sinh ra phải là giờ địa phương của bệnh nhân."""
        doses = solve(rx(item("Metformin", 1, meal="after_meal")), routine)
        t = to_minutes(doses[0]["time"])
        # Sau bữa sáng 07:00 giờ VN
        assert 7 * 60 <= t <= 8 * 60

    def test_different_timezone(self):
        """Bệnh nhân đi Nhật — lịch sinh hoạt theo giờ Nhật."""
        jp = {
            "wake_time": "06:00", "breakfast_time": "07:00",
            "lunch_time": "12:00", "dinner_time": "19:00",
            "bed_time": "22:00", "timezone": "Asia/Tokyo",
        }
        doses = solve(rx(item("Metformin", 1, meal="after_meal")), jp)
        assert len(doses) == 1