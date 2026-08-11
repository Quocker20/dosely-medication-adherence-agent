"""Demo: mock 1 don thuoc + 1 lich sinh hoat, chay compute_schedule, in JSON.

Khong goi LLM, khong goi backend that - chi de xem compute_schedule hoat
dong dung tren du lieu gia lap. Chay tu thu muc goc repo (src-layout can -m):
python -m scripts.demo_compute_schedule
"""
import json

from src.agents.scheduling import compute_schedule

# Gia lap PatientRoutineResponse (schema.md 4.3)
mock_routine = {
    "wake_time": "06:30:00",
    "breakfast_time": "07:00:00",
    "lunch_time": "12:00:00",
    "dinner_time": "18:30:00",
    "sleep_time": "22:30:00",
}

# Gia lap PrescriptionDetailResponse.items (schema.md 5.5) - 2 thuoc
mock_prescription_items = [
    {
        "id": "item-metformin",
        "display_name": "Metformin 850mg",
        "dose_unit": "VIEN",
        "morning_dose": 1,
        "noon_dose": None,
        "evening_dose": 1,
        "bedtime_dose": None,
        "meal_relation": "AFTER_MEAL",
        "minimum_interval_minutes": None,
        "start_date": "2026-08-01",
        "end_date": None,
        "instructions": "Uong ngay sau khi an de tranh kich ung da day",
    },
    {
        "id": "item-amlodipine",
        "display_name": "Amlodipine 5mg",
        "dose_unit": "VIEN",
        "morning_dose": None,
        "noon_dose": None,
        "evening_dose": None,
        "bedtime_dose": 1,
        "meal_relation": None,
        "minimum_interval_minutes": None,
        "start_date": "2026-08-01",
        "end_date": "2026-12-31",
        "instructions": "Uong truoc khi ngu",
    },
]

if __name__ == "__main__":
    schedule = compute_schedule(
        mock_prescription_items,
        mock_routine,
        target_date="2026-08-11",
        timezone="Asia/Ho_Chi_Minh",
    )
    print(json.dumps(schedule, ensure_ascii=False, indent=2))
