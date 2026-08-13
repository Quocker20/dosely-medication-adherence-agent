"""Demo: doc 2 file JSON gia lap (don thuoc + lich sinh hoat), chay
compute_schedule, in ra lich uong thuoc ca nhan hoa dang JSON.

Khong goi LLM, khong goi backend - chi chay tang 1 (constraint solver)
tren du lieu gia lap trong scripts/mock_prescription.json va
scripts/mock_routine.json.

Chay tu thu muc goc repo (src-layout can -m):
    python -m scripts.demo_compute_schedule
"""
import json
from itertools import groupby
from pathlib import Path

from src.agents.nodes.compute_schedule import compute_schedule

_DIR = Path(__file__).parent


def _print_grouped_by_time(schedule: list[dict]) -> None:
    """In theo từng lần uống thuốc: 1 giờ có thể gồm nhiều loại thuốc."""
    for time, doses in groupby(schedule, key=lambda d: d["time"]):
        drugs = ", ".join(d["drug"] for d in doses)
        print(f"{time}  ->  {drugs}")


if __name__ == "__main__":
    prescription = json.loads((_DIR / "mock_prescription.json").read_text(encoding="utf-8"))
    routine = json.loads((_DIR / "mock_routine.json").read_text(encoding="utf-8"))

    schedule = compute_schedule(prescription, routine, target_date="2026-08-13")

    print("=== Lich uong thuoc theo tung lan (gop theo gio) ===")
    _print_grouped_by_time(schedule)

    print("\n=== JSON day du (1 phan tu / thuoc) ===")
    print(json.dumps(schedule, ensure_ascii=False, indent=2))
