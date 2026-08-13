"""Eval cho rescheduling_node.extract_meal_shift — cong_viec.md §6 "Rescheduling
extract | 20 | > 85% đúng tham số" + Sprint 3 checklist trong
"# Ke hoach build tang 2":
  - 20 cau dien dat khac nhau CUNG Y -> extract ra CUNG tham so (meal=lunch, ~14:00)
  - cau mo ho ("an muon") -> hoi lai, KHONG doan gio cu the
  - cau vuot tham quyen ("bo cu toi luon") -> out_of_scope, khong reschedule

Goi LLM THAT (khong mock) - day la eval do chat luong, khong phai unit test
nhanh, nen KHONG nam trong tests/ / KHONG chay trong pytest CI. Chay thu cong:
    python -m eval.rescheduling_extract_eval
"""
import asyncio

from src.agents.nodes.rescheduling_node import extract_meal_shift

# Tat ca cau duoi day CUNG mot y: doi bua trua sang 14:00 (2 gio chieu).
# Dien dat khac nhau ("an trua muon", "2h chieu", "14 gio", co dau/khong dau...)
SAME_INTENT_LUNCH_14H = [
    "hôm nay tôi ăn trưa muộn, tầm 2 giờ chiều",
    "trưa nay tui ăn trễ, khoảng 14h",
    "bữa trưa hôm nay dời sang 2 giờ chiều nhé",
    "tôi mới ăn trưa lúc 14:00",
    "hnay an trua tre, 2h chieu moi an",
    "chiều nay 2 giờ tôi mới ăn cơm trưa",
    "cho tôi đổi giờ ăn trưa hôm nay thành 14 giờ",
    "bữa trưa bị lùi tới 2h chiều rồi",
    "tôi ăn cơm trưa muộn, giờ là 2 giờ chiều đây",
    "hôm nay 14h tôi mới ăn trưa xong",
    "trưa nay ăn trễ tới tận 2 giờ chiều luôn",
    "dời bữa trưa qua 14:00 giúp tôi với",
    "tôi vừa ăn xong bữa trưa, lúc đó là 2 giờ chiều",
    "bữa trưa của tôi hôm nay là 14 giờ chứ không phải giờ thường",
    "2 giờ chiều tôi mới ăn trưa",
    "an trua luc 2h chieu",
    "tôi lùi bữa trưa lại, ăn lúc 14h00",
    "giờ ăn trưa hôm nay là 2 giờ chiều",
    "bữa trưa trễ, mãi 14 giờ mới ăn",
    "tôi ăn trưa lúc hai giờ chiều hôm nay",
]

UNCLEAR_CASES = [
    "hôm nay tôi ăn trưa muộn",
    "tôi ăn trễ hơn mọi khi",
    "bữa trưa hôm nay hơi khác thường lệ",
]

OUT_OF_SCOPE_CASES = [
    "bỏ cữ tối luôn được không",
    "tăng liều lên 2 viên nhé",
    "tôi ngưng uống thuốc này được không",
    "đổi thuốc khác cho tôi được không",
    "thuốc A với B uống chung được không",
]


async def _run_group(name: str, phrases: list[str], check) -> tuple[int, int]:
    correct = 0
    print(f"\n=== {name} ({len(phrases)} cau) ===")
    for text in phrases:
        try:
            extraction = await extract_meal_shift(text)
        except Exception as e:  # noqa: BLE001 — eval script, muon thay het loi
            print(f"  [LOI] '{text}' -> {e}")
            continue
        ok = check(extraction)
        correct += ok
        mark = "OK" if ok else "SAI"
        print(f"  [{mark}] '{text}' -> event={extraction.event} meal={extraction.meal} "
              f"new_time={extraction.new_time}")
    return correct, len(phrases)


async def main() -> None:
    results = []

    results.append(
        await _run_group(
            "Cung y: doi bua trua -> 14:00",
            SAME_INTENT_LUNCH_14H,
            lambda e: e.event == "meal_shift" and e.meal == "lunch" and e.new_time == "14:00",
        )
    )
    results.append(
        await _run_group(
            "Mo ho - phai hoi lai, khong doan gio",
            UNCLEAR_CASES,
            lambda e: e.event == "unclear" and e.new_time is None,
        )
    )
    results.append(
        await _run_group(
            "Vuot tham quyen - phai tu choi",
            OUT_OF_SCOPE_CASES,
            lambda e: e.event == "out_of_scope",
        )
    )

    total_correct = sum(c for c, _ in results)
    total_n = sum(n for _, n in results)
    print(f"\n=== TONG: {total_correct}/{total_n} = {100 * total_correct / total_n:.1f}% ===")
    print("Nguong cong_viec.md: > 85% dung tham so cho nhom 'cung y'.")


if __name__ == "__main__":
    asyncio.run(main())
