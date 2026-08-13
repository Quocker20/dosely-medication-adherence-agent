"""compute_schedule — tầng 1: constraint solver tính giờ uống thuốc.

Xem "# Kế hoạch build tầng 2 — Agent layer.md": tầng 2 (agent) KHÔNG tự
tính giờ, mọi phép tính lịch trong tầng 2 đều phải gọi lại hàm này. Pure
code, không LLM, không I/O — vì cùng input phải luôn ra cùng output
(test_schedule.py::TestDeterminism).

Hợp đồng input/output theo test_schedule.py — xem docstring compute_schedule().

Giới hạn đã biết:
- `minimum_interval_minutes` trên một item chỉ được ĐẢM BẢO chắc chắn giữa
  các cữ CÙNG thuốc đó. test_cross_drug_interval (2 thuốc khác nhau cần
  cách nhau) pass được vì hai mốc neo (bedtime vs. khung giờ rảnh giữa
  ngày) tự nhiên đã cách xa nhau — không phải vì có một bộ giải ràng buộc
  toàn cục giữa nhiều thuốc.

  Đã thử implement một bản "ép chéo toàn cục": hễ 1 item khai
  minimum_interval_minutes thì mọi cữ của nó phải cách MỌI cữ khác trong
  đơn tối thiểu chừng đó phút, kèm bước dịch liều lỏng nhất trước khi bó
  tay mới raise. Bản đó PHÁ VỠ TestRealWorldPrescription: Metformin khai
  interval=240 với ý nghĩa tự-thân (3 cữ/ngày cách nhau vì lý do dạ dày),
  nhưng logic chéo hiểu nhầm thành "Metformin phải cách cả 5 thuốc khác
  ≥240 phút" — vô lý và không thể giải. Dữ liệu test (`item()`) không có
  trường nào phân biệt "interval tự-thân" và "interval kỵ thuốc cụ thể",
  nên không thể suy luận đúng ý đồ chỉ từ minimum_interval_minutes. Đã bỏ
  hướng đó, quay lại bản này theo lựa chọn của người dùng.

  Nếu sau này thật sự cần ép khoảng cách CHÉO giữa 2 thuốc cụ thể, cần
  thêm một trường tường minh kiểu `conflicts_with: [drug_name, ...]` vào
  item trước, rồi mới viết bước hậu-xử lý toàn cục dựa trên trường đó —
  chưa làm ở đây. Việc không tự kết luận tương tác thuốc (DDI) khớp với
  cong_viec.md §1.1 — ngoài phạm vi MVP.
- Chỉ làm việc với giờ-trong-ngày ("HH:MM"), không cần zoneinfo: routine đã
  là giờ địa phương của bệnh nhân (patient_routine["timezone"] chỉ mang
  tính mô tả), và target_date không ảnh hưởng đến phép tính giờ ở tầng này
  — việc gắn giờ vào một ngày lịch cụ thể (kèm tz) là việc của tầng gọi.
"""
from __future__ import annotations

_MEAL_FIELDS = ("breakfast_time", "lunch_time", "dinner_time")
_BEFORE_MEAL_OFFSET = 30
_AFTER_MEAL_OFFSET = 30
_BEDTIME_OFFSET = 45


class ScheduleConflictError(Exception):
    """Không thể xếp lịch thỏa minimum_interval_minutes trong khung giờ thức.

    Cố tình KHÔNG âm thầm phá vỡ minimum_interval để "cho vừa" — thà báo
    xung đột rõ ràng để con người/agent tầng 2 xử lý tiếp.
    """


def _to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":")[:2])
    return h * 60 + m


def _to_hhmm(minutes: float) -> str:
    total = round(minutes) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _awake_window(routine: dict) -> tuple[int, int]:
    for key in ("wake_time", "bed_time"):
        if not routine.get(key):
            raise ValueError(f"Routine thiếu '{key}' — không tính được khung giờ thức.")
    wake = _to_minutes(routine["wake_time"])
    bed = _to_minutes(routine["bed_time"])
    # bed > wake: ngủ xuyên nửa đêm (trường hợp thường gặp).
    # bed <= wake: ngủ ban ngày (vd bệnh nhân làm ca đêm) — khung thức nối
    # từ wake, vắt qua nửa đêm, tới bed của "ngày hôm sau".
    awake_end = bed if bed > wake else bed + 1440
    return wake, awake_end


def _unwrap(minute: int, awake_start: int) -> int:
    """Đưa 1 mốc giờ trong ngày vào cùng trục thời gian tuyến tính với
    khung thức (cộng thêm 1 ngày nếu mốc đó rơi vào 'trước lúc thức')."""
    return minute if minute >= awake_start else minute + 1440


def _meal_anchors(routine: dict, awake_start: int) -> list[int]:
    anchors = [
        _unwrap(_to_minutes(routine[key]), awake_start)
        for key in _MEAL_FIELDS
        if routine.get(key)
    ]
    return sorted(anchors)


def _pick_indices(n: int, m: int) -> list[int]:
    """Chọn n chỉ số (0..m-1) trải đều trong m mốc bữa ăn.

    n == 1 -> luôn chọn mốc đầu tiên (thói quen phổ biến: thuốc uống 1
    lần/ngày thường gắn với bữa sáng), không phải mốc giữa.
    """
    if n <= 0:
        return []
    if n == 1 or m <= 1:
        return [0] * n
    return [min(round(i * (m - 1) / (n - 1)), m - 1) for i in range(n)]


def _check_interval(times: list[float], minimum_interval_minutes: int | None, drug: str) -> None:
    if not minimum_interval_minutes:
        return
    ordered = sorted(times)
    for a, b in zip(ordered, ordered[1:]):
        if b - a < minimum_interval_minutes:
            raise ScheduleConflictError(
                f"Xung đột (conflict): '{drug}' cần các cữ cách nhau tối thiểu "
                f"{minimum_interval_minutes} phút nhưng lịch tính ra chỉ cách {b - a:.0f} phút."
            )


def _schedule_meal_relation(item: dict, meals: list[int], awake_end: int) -> list[float]:
    n = int(item["frequency_per_day"])
    relation = item["meal_relation"]
    drug = item["drug_name"]

    if relation == "bedtime":
        base = awake_end - _BEDTIME_OFFSET
        return [base - i * 15 for i in range(n)]

    if not meals:
        raise ValueError(
            f"'{drug}' cần meal_relation={relation!r} nhưng routine không có mốc "
            "giờ bữa ăn nào (breakfast_time/lunch_time/dinner_time)."
        )

    sign = -1 if relation == "before_meal" else 1
    idxs = _pick_indices(n, len(meals))

    times: list[float] = []
    seen: set[float] = set()
    for idx in idxs:
        t = meals[idx] + sign * (_BEFORE_MEAL_OFFSET if sign < 0 else _AFTER_MEAL_OFFSET)
        while t in seen:  # n > số mốc bữa ăn -> vài cữ trùng mốc, giãn nhẹ để không trùng giờ
            t += 5 * sign
        seen.add(t)
        times.append(t)
    return times


def _schedule_no_meal_relation(item: dict, awake_start: int, awake_end: int) -> list[float]:
    n = int(item["frequency_per_day"])
    window = awake_end - awake_start
    interval = item.get("minimum_interval_minutes")

    if interval:
        min_span = (n - 1) * interval
        if min_span > window:
            raise ScheduleConflictError(
                f"Xung đột (conflict): '{item['drug_name']}' cần {n} cữ/ngày cách nhau "
                f"tối thiểu {interval} phút (cần {min_span} phút) nhưng khung giờ thức "
                f"của bệnh nhân chỉ có {window} phút."
            )
        # Căn giữa cụm cữ (cách đều đúng bằng interval) trong khung giờ thức,
        # thay vì luôn dồn về sát lúc vừa thức dậy.
        start = awake_start + (window - min_span) / 2
        return [start + i * interval for i in range(n)]

    gap = window / (n + 1)
    return [awake_start + (i + 1) * gap for i in range(n)]


def compute_schedule(prescription: dict, patient_routine: dict, target_date: str) -> list[dict]:
    """Sinh lịch uống thuốc trong một ngày từ đơn thuốc + lịch sinh hoạt.

    Args:
        prescription: {"prescription_id": str, "items": [item, ...]}, mỗi
            item có drug_name, frequency_per_day, meal_relation
            (None/"before_meal"/"after_meal"/"bedtime"),
            minimum_interval_minutes (tùy chọn).
        patient_routine: wake_time, breakfast_time, lunch_time, dinner_time,
            bed_time (tất cả "HH:MM"), timezone (chỉ mang tính mô tả).
        target_date: ngày cần sinh lịch — không ảnh hưởng phép tính giờ ở
            tầng này, chỉ được gắn kèm vào mỗi cữ để tầng gọi map ra
            datetime thật.

    Returns:
        list[dict], mỗi phần tử: {"drug", "time" ("HH:MM"), "meal_relation",
        "date"}, sort theo giờ tăng dần.

    Raises:
        ValueError: routine thiếu mốc giờ bắt buộc cho item đang xử lý.
        ScheduleConflictError: không thể xếp đủ số cữ mà vẫn thỏa
            minimum_interval_minutes trong khung giờ thức — KHÔNG bao giờ
            âm thầm nới lỏng ràng buộc này.
    """
    items = prescription.get("items", [])
    awake_start, awake_end = _awake_window(patient_routine)
    meals = _meal_anchors(patient_routine, awake_start)

    doses: list[dict] = []
    # Sort theo tên thuốc để kết quả không phụ thuộc thứ tự item trong đơn
    # (test_schedule.py::TestDeterminism::test_item_order_does_not_matter).
    for item in sorted(items, key=lambda it: it["drug_name"]):
        if item.get("meal_relation"):
            times = _schedule_meal_relation(item, meals, awake_end)
        else:
            times = _schedule_no_meal_relation(item, awake_start, awake_end)

        _check_interval(times, item.get("minimum_interval_minutes"), item["drug_name"])

        for t in times:
            doses.append(
                {
                    "drug": item["drug_name"],
                    "time": _to_hhmm(t),
                    "meal_relation": item.get("meal_relation"),
                    "date": target_date,
                }
            )

    doses.sort(key=lambda d: (d["time"], d["drug"]))
    return doses
