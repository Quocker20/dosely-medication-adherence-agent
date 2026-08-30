"""100 non-schedule semantic cases, executed through the real LLM graph."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agents.graph import agent

ROOT = Path(__file__).resolve().parents[1]

TEMPLATES = [
 ("ask_drug_info", "{drug} thường để làm gì vậy, giải thích kiểu dễ hiểu hộ mình"),
 ("ask_drug_info", "nghe nói {typo} có thể gây {symptom}, chuyện đó đúng trong kiến thức thuốc không?"),
 ("ask_drug_info", "nếu một người dùng {drug} mà thấy {symptom} thì đó có nằm trong phản ứng bất lợi đã biết không"),
 ("ask_drug_info", "{drug} dùng chung với đồ ăn hay thuốc khác có điều gì cần thận trọng"),
 ("ask_drug_info", "mình không bảo là đang mắc nhé, chỉ muốn biết {drug} có chống chỉ định nào"),
 ("report_adverse_event", "không biết có liên quan không nhưng từ khi dùng thuốc tôi thực sự bị {symptom}"),
 ("report_adverse_event", "mấy hôm nay người cứ {symptom}, tôi đang uống thuốc theo đơn, ghi nhận giúp bác sĩ xem"),
 ("report_adverse_event", "toi dang bi {typo_symptom} sau khi uong thuoc, chua chac thuoc gay ra"),
 ("clarify", "cái viên ấy ấy, tôi muốn hỏi mà không nhớ tên cũng chẳng nhớ đặc điểm"),
 ("general", "tôi có thể nhờ RemindRx hỗ trợ những việc gì liên quan đến thuốc?"),
]

VALUES = [
 {"drug":"Paracetamol","typo":"paracetmol","symptom":"đau bụng","typo_symptom":"dau bung"},
 {"drug":"Amoxicillin","typo":"amoxcilin","symptom":"buồn nôn","typo_symptom":"buon non"},
 {"drug":"Doxycycline","typo":"doxyciclin","symptom":"chóng mặt","typo_symptom":"chong mat"},
 {"drug":"Cetirizine","typo":"cetirizin","symptom":"khô miệng","typo_symptom":"kho mieng"},
 {"drug":"Warfarin","typo":"wafarin","symptom":"bầm tím","typo_symptom":"bam tim"},
 {"drug":"Calcium gluconate","typo":"calci gluconat","symptom":"ngứa","typo_symptom":"ngua"},
 {"drug":"Vitamin C","typo":"vitamin xê","symptom":"tiêu chảy","typo_symptom":"tieu chay"},
 {"drug":"Isosorbide dinitrate","typo":"isosorbit dinitrat","symptom":"đau đầu","typo_symptom":"dau dau"},
 {"drug":"A Doxid 100mg Capsule","typo":"a doxit","symptom":"nổi mẩn","typo_symptom":"noi man"},
 {"drug":"A-CN Gel","typo":"a cn jel","symptom":"mệt bất thường","typo_symptom":"met bat thuong"},
]


def cases():
    return [{"id": f"NS{idx*10+j+1:03d}", "expected_intent": intent,
             "question": template.format(**value)}
            for idx, (intent, template) in enumerate(TEMPLATES)
            for j, value in enumerate(VALUES)]


async def main():
    load_dotenv(ROOT / ".env")
    for key in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"):
        os.environ.pop(key, None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    selected = cases()
    only = {item.strip() for item in os.getenv("EVAL_ONLY", "").split(",") if item.strip()}
    if only:
        selected = [case for case in selected if case["id"] in only]
    results = []
    for case in selected:
        try:
            state = await agent.ainvoke({"messages":[HumanMessage(content=case["question"])], "patient_id":"eval-patient"})
            answer = str(state.get("messages", [])[-1].content)
            actual = state.get("intent")
            passed = actual == case["expected_intent"] and bool(answer.strip())
            row = {**case, "actual_intent":actual, "answer":answer, "passed":passed, "error":None}
        except Exception as exc:
            row = {**case, "actual_intent":None, "answer":"", "passed":False,
                   "error":f"{type(exc).__name__}: {exc}"}
        results.append(row)
        print(f"[{row['id']}] {'PASS' if row['passed'] else 'FAIL'} {row['actual_intent']} | {row['question']}")
    out = ROOT / "eval" / "results" / "non_schedule_100_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(x["passed"] for x in results)
    total = len(results)
    print(f"SCORE={passed}/{total} ({round(100 * passed / total) if total else 0}%) RESULT={out}")

if __name__ == "__main__":
    asyncio.run(main())
