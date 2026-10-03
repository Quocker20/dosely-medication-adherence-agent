"""100 non-schedule semantic cases, executed through the real LLM graph."""
from __future__ import annotations
import asyncio, json, os, sys
from datetime import datetime
from pathlib import Path

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from src.agents.graph import agent
from src.modules.planning.core.llm import get_llm

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
 ("general", "tôi có thể nhờ Dosely hỗ trợ những việc gì liên quan đến thuốc?"),
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


class HallucinationVerdict(BaseModel):
    applicable: bool
    hallucinated: bool
    confidence: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list)
    reason: str


JUDGE_PROMPT = """Bạn là giám khảo factuality cho chatbot y tế. So sánh CÂU TRẢ LỜI với NGUỒN.
Tuyệt đối không được lấy nội dung hoặc tiền đề trong CÂU HỎI làm claim của chatbot.
unsupported_claims chỉ được chép các mệnh đề thực sự xuất hiện trong CÂU TRẢ LỜI.
Không xem lời cảnh báo chung, yêu cầu hỏi lại hoặc thông báo không đủ dữ liệu là hallucination.
Với kiến thức thuốc, mọi khẳng định y khoa cụ thể phải được nguồn hỗ trợ. Nếu không có nguồn mà câu trả lời
vẫn khẳng định công dụng/tác dụng phụ/chống chỉ định/tương tác thì hallucinated=true.
Với báo cáo triệu chứng, chỉ chấm việc chatbot có bịa triệu chứng, thuốc, nguyên nhân hay chẩn đoán hay không.
Không suy diễn kiến thức ngoài phần NGUỒN. Trả kết quả đúng schema."""


async def judge_hallucination(case: dict, row: dict) -> HallucinationVerdict:
    if row.get("actual_intent") in {"general", "clarify"}:
        return HallucinationVerdict(applicable=False, hallucinated=False, confidence=1,
                                    reason="Không có khẳng định y khoa cần đối chiếu.")
    sources = row.get("rag_sources") or []
    payload = {
        "question": case["question"], "intent": row.get("actual_intent"),
        "answer": row.get("answer"), "grounding_valid": row.get("grounding_valid"),
        "sources": sources,
    }
    judge = get_llm(temperature=0).with_structured_output(HallucinationVerdict)
    return await judge.ainvoke([
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])


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
            row = {**case, "actual_intent":actual, "answer":answer, "passed":passed,
                   "grounding_valid":state.get("grounding_valid"),
                   "grounding_errors":state.get("grounding_errors") or [],
                   "rag_sources":state.get("rag_sources") or [], "error":None}
        except Exception as exc:
            row = {**case, "actual_intent":None, "answer":"", "passed":False,
                   "error":f"{type(exc).__name__}: {exc}"}
        try:
            verdict = await judge_hallucination(case, row)
            row["hallucination"] = verdict.model_dump()
        except Exception as exc:
            row["hallucination"] = {"applicable":True, "hallucinated":None,
                                      "confidence":0, "unsupported_claims":[],
                                      "reason":f"judge_error: {type(exc).__name__}: {exc}"}
        results.append(row)
        print(f"[{row['id']}] {'PASS' if row['passed'] else 'FAIL'} {row['actual_intent']} | {row['question']}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "eval" / "results" / f"non_schedule_100_live_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(x["passed"] for x in results)
    hallucinated = sum(x.get("hallucination", {}).get("hallucinated") is True for x in results)
    total = len(results)
    print(f"SCORE={passed}/{total} ({round(100 * passed / total) if total else 0}%) RESULT={out}")
    print(f"HALLUCINATION={hallucinated}/{total}")

if __name__ == "__main__":
    asyncio.run(main())
