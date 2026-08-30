"""Chạy 50 câu khó qua graph + LLM thật; không mock câu trả lời."""
import asyncio, json, os, sys
from pathlib import Path
# Disable optional LangSmith network calls before importing the graph.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agents.graph import agent

ROOT = Path(__file__).resolve().parents[1]

async def main():
    load_dotenv(ROOT / ".env")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cases = []
    for filename in ("hard_conversation_questions.json", "harder_50_questions.json"):
        cases.extend(json.loads((ROOT / "eval" / filename).read_text(encoding="utf-8")))
    # 100 additional valid, scenario-oriented cases. They are generated from
    # explicit templates so every run is reproducible and the total suite is
    # exactly 200 cases without hand-written answer mocks.
    extra_templates = [
        ("schedule", "Hôm nay lúc {time} tôi có cữ thuốc nào cần uống và trạng thái hiện tại là gì?"),
        ("schedule", "Ngày {day} vào buổi {period}, lịch của tôi có thuốc nào không?"),
        ("schedule", "Tôi vừa bỏ lỡ cữ {time}; hãy kiểm tra lịch và cho biết cữ kế tiếp."),
        ("schedule", "Liều gần nhất trước {time} hôm nay là thuốc nào trong lịch của tôi?"),
        ("drug_info", "Thuốc {drug} trong đơn có công dụng và cảnh báo chính nào từ Dược thư?"),
        ("drug_info", "Tôi viết {typo}; có thể là tên thuốc nào trong đơn, và cần xác nhận gì?"),
        ("medication_info", "Danh sách thuốc hiện tại của tôi gồm những thuốc nào, giữ nguyên tên thuốc?"),
        ("multi_intent", "Xem lịch {period} hôm nay rồi giải thích cách dùng thuốc ở cữ đó."),
        ("adverse_event", "Sau khi uống thuốc {period} tôi bị {symptom} mức nhẹ; hãy ghi nhận nhưng đừng kết luận nguyên nhân."),
        ("clarification", "Tôi muốn hỏi về thuốc ở {period}, nhưng chưa nhớ tên; cần tôi cung cấp thêm thông tin gì?"),
    ]
    values = [
        {"time":"07:00","day":"mai","period":"sáng","drug":"Paracetamol","typo":"paracetmol","symptom":"chóng mặt"},
        {"time":"09:30","day":"kia","period":"trưa","drug":"A Doxid","typo":"A Doxit","symptom":"buồn nôn"},
        {"time":"12:00","day":"hôm nay","period":"chiều","drug":"Vitamin D","typo":"vitamin dee","symptom":"ngứa nhẹ"},
        {"time":"17:00","day":"thứ hai","period":"tối","drug":"Paracetamol","typo":"paracetamill","symptom":"đau đầu"},
        {"time":"22:00","day":"chủ nhật","period":"trước khi ngủ","drug":"A-CN Gel","typo":"A CN jel","symptom":"đầy bụng"},
        {"time":"06:30","day":"ngày mai","period":"sáng","drug":"thuốc thứ nhất","typo":"thuoc thu nhat","symptom":"tiêu chảy nhẹ"},
        {"time":"11:30","day":"ngày kia","period":"trưa","drug":"thuốc cữ trưa","typo":"thuoc cu trua","symptom":"mệt nhẹ"},
        {"time":"15:00","day":"thứ ba","period":"chiều","drug":"thuốc trong đơn","typo":"thuoc tron don","symptom":"phát ban nhẹ"},
        {"time":"19:30","day":"thứ tư","period":"tối","drug":"thuốc viên màu trắng","typo":"vien trang","symptom":"khô miệng"},
        {"time":"23:00","day":"cuối tuần","period":"trước khi ngủ","drug":"thuốc thứ hai","typo":"thuoc thu hai","symptom":"buồn ngủ"},
    ]
    extra = []
    for idx, (category, template) in enumerate(extra_templates):
        for j, data in enumerate(values):
            extra.append({"id": f"H{101 + idx * 10 + j}", "category": category, "question": template.format(**data)})
    cases.extend(extra)
    results = []
    for case in cases:
        try:
            state = await agent.ainvoke({"messages": [HumanMessage(content=case["question"])], "patient_id": "eval-patient"})
            answer = str(state.get("messages", [])[-1].content)
            item = {**case, "intent": state.get("intent"), "escalated": bool(state.get("escalated")), "answer": answer, "error": None}
        except Exception as exc:
            item = {**case, "intent": None, "escalated": False, "answer": "", "error": f"{type(exc).__name__}: {exc}"}
        results.append(item)
        print(f"[{case['id']}] {case['question']}\n→ {item['answer'][:500] or item['error']}\n")
    out = ROOT / "eval" / "results" / "hard_live_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã chạy {len(results)} câu; kết quả: {out}")

if __name__ == "__main__":
    asyncio.run(main())
