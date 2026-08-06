# Phân tích nội dung Drive & Đặc tả MVP Nâng cao (v2) — AdhereMind

## Tổng quan

Tài liệu này kế thừa phân tích từ phiên bản 1, đồng thời bổ sung các tính năng, ràng buộc an toàn y khoa (Medical Safety Guardrails) và chi tiết hóa hoạt động của các AI Agent nhằm xây dựng một MVP **AdhereMind — Web-App hỗ trợ tuân thủ điều trị cho người cao tuổi** hoàn chỉnh, an toàn và sẵn sàng cho việc triển khai thực tế.

---

## 1. Bài toán và Phân nhóm Người dùng (Persona)

AdhereMind kết nối chặt chẽ ba nhóm đối tượng bằng cơ chế phân quyền rõ ràng:

1. **Bác sĩ điều trị (Doctor):**
   - Kê đơn, duyệt đơn thuốc đã được số hóa từ ảnh chụp.
   - Theo dõi mức độ tuân thủ điều trị và nhận cảnh báo khi có biến cố bất thường của bệnh nhân.
2. **Bệnh nhân (Patient - Người cao tuổi):**
   - Nhận nhắc nhở uống thuốc thông minh.
   - Báo cáo trạng thái uống thuốc và khảo sát sức khỏe hàng ngày.
   - Tương tác bằng giọng nói hoặc giao diện tối giản (Accessible UI).
3. **Người chăm sóc/Người thân (Caregiver):**
   - Theo dõi trạng thái dùng thuốc thời gian thực của bệnh nhân.
   - Nhận tin nhắn cảnh báo khẩn cấp và có thể xác nhận đã hỗ trợ bệnh nhân uống thuốc.

---

## 2. Các chức năng MVP Nâng cao (Bản v2)

Các chức năng dưới đây đã được tinh chỉnh để giải quyết các khoảng trống về **An toàn y khoa** và **Trải nghiệm người cao tuổi (UX)**:

### 2.1. Phân hệ Bác sĩ (Doctor Portal)
- **Đăng nhập chuyên môn:** Email/Mật khẩu hoặc liên kết hệ thống bệnh viện.
- **Kê đơn thuốc điện tử (Prescription Management):**
  - Nhập trực tiếp đơn thuốc hoặc tải file ảnh/PDF đơn thuốc.
  - **AI OCR & Auto-Parsing:** Trích xuất tên thuốc, liều lượng, tần suất, thời điểm uống (trước/sau ăn) thành cấu trúc JSON chuẩn hóa.
  - **Human-in-the-loop:** Bác sĩ bắt buộc phải xem lại thông tin trích xuất của AI và nhấn "Xác nhận & Ký số" trước khi áp dụng cho bệnh nhân.
- **Kiểm tra tương tác thuốc (Drug Interaction Check - RAG/Knowledge):**
  - Hệ thống tự động so khớp đơn thuốc mới với các đơn thuốc hiện tại của bệnh nhân.
  - Tra cứu qua cơ sở dữ liệu y khoa (RAG) để phát hiện tương tác thuốc có hại (Drug-Drug Interactions) hoặc chống chỉ định (Contraindications). Cảnh báo đỏ sẽ xuất hiện trên màn hình kê đơn để bác sĩ thay đổi nếu cần.
- **Dashboard Giám sát Tuân thủ (Adherence Monitor):**
  - Biểu đồ tỷ lệ tuân thủ theo thời gian thực (Compliance Rate = số lần uống đúng giờ / tổng số lần nhắc).
  - Phân loại bệnh nhân theo mức độ rủi ro (Xanh: Tuân thủ tốt >80%, Vàng: Cần lưu ý 50-80%, Đỏ: Nguy cơ cao <50% hoặc bỏ thuốc >3 lần liên tiếp).

### 2.2. Phân hệ Bệnh nhân (Patient Web-App/PWA)
- **Đăng nhập tối giản:** Số điện thoại + OTP (hỗ trợ tự động điền) hoặc Đăng nhập nhanh qua liên kết mời gửi đến Zalo/SMS.
- **Accessible UI/UX (Thiết kế cho người cao tuổi):**
  - Phông chữ lớn, độ tương phản cao, nút bấm lớn.
  - Hỗ trợ **Text-to-Speech (TTS):** Đọc to tên thuốc và hướng dẫn uống (ví dụ: "Đã đến giờ uống 1 viên thuốc huyết áp màu vàng sau ăn").
  - Hỗ trợ **Voice Survey:** Bệnh nhân trả lời khảo sát sức khỏe hàng ngày bằng giọng nói (AI tự động chuyển thành văn bản và trích xuất triệu chứng).
- **Lập lịch tự động (Planning Agent):**
  - Bệnh nhân (hoặc người thân) chỉ cần cấu hình giờ sinh hoạt cơ bản (giờ thức dậy, giờ ăn sáng, ăn trưa, ăn tối, giờ đi ngủ).
  - Planning Agent sẽ tự động phân phối lịch uống thuốc phù hợp với giờ sinh hoạt và hướng dẫn của bác sĩ (ví dụ: thuốc uống sau ăn sáng 30 phút).
- **Nhắc nhở thông minh & Ghi nhận trạng thái:**
  - Nhắc nhở qua Web Push Notification (hoặc SMS/Zalo nếu mất kết nối mạng hoặc không phản hồi sau 15 phút).
  - Ba nút trạng thái rõ ràng: **[Đã uống]**, **[Uống muộn]**, **[Bỏ qua]**.
  - **Offline-First Support:** Lịch uống thuốc được lưu trong Service Worker/Local Storage, vẫn đổ chuông/nhắc nhở khi mất mạng. Khi có mạng trở lại sẽ đồng bộ log về server.
- **Khảo sát sức khỏe hàng ngày (Daily Health Survey Agent):**
  - Khảo sát nhanh 3-5 câu hỏi về cảm giác sau khi uống thuốc và các tác dụng phụ phổ biến.
  - Sử dụng AI để phát hiện các triệu chứng bất thường.
- **Nút khẩn cấp (SOS Button):**
  - Đặt ở vị trí dễ thấy nhất trên màn hình chính. Khi nhấn sẽ kích hoạt ngay lập tức chuỗi cảnh báo SOS.

### 2.3. Phân hệ Người chăm sóc (Caregiver Companion)
- **Dashboard giám sát người thân:** Xem lịch trình uống thuốc trong ngày, xem lịch sử và tỷ lệ tuân thủ của bệnh nhân.
- **Xác nhận hộ (Caregiver Override):** Cho phép người chăm sóc bấm "Xác nhận đã cho bệnh nhân uống" trong trường hợp người cao tuổi không biết sử dụng ứng dụng.

---

## 3. Luồng cảnh báo và Ràng buộc an toàn y khoa (Medical Safety Guardrails)

Để đảm bảo AI không gây nguy hiểm cho tính mạng của bệnh nhân, các cơ chế dưới đây được thiết lập cứng (Hardcoded rules) kết hợp với AI giám sát:

### 3.1. Luồng xử lý Bỏ thuốc / Uống muộn (Rescheduling Agent Guardrails)
Khi bệnh nhân báo **[Uống muộn]** hoặc không phản hồi đúng giờ:
1. **Không tự ý gộp liều (No Double Dosing):** Nếu uống muộn quá gần với thời gian của liều tiếp theo, Rescheduling Agent **không bao giờ** được đề xuất uống gấp đôi liều tiếp theo.
2. **Khoảng cách tối thiểu (Min Time Gap):** Giữa hai liều của cùng một hoạt chất phải cách nhau một khoảng thời gian tối thiểu theo quy định y khoa (ví dụ: thuốc huyết áp cách nhau ít nhất 8 tiếng). Nếu liều 1 bị muộn quá nhiều, liều 2 sẽ được dời đi hoặc hệ thống sẽ đề xuất bỏ qua liều 2 và báo cáo bác sĩ.
3. **Khung giờ sinh hoạt (Sleep Window):** Tránh xếp lịch uống thuốc vào khoảng thời gian ngủ của bệnh nhân (trừ các loại thuốc đặc biệt yêu cầu uống ban đêm).
4. **Giới hạn số lần Reschedule:** Hệ thống chỉ tự động dời lịch tối đa 2 lần/ngày. Nếu bệnh nhân tiếp tục trễ giờ hoặc bỏ qua liều thứ 3 liên tiếp, hệ thống sẽ **khóa chức năng tự điều chỉnh lịch** và chuyển sang luồng cảnh báo khẩn cấp (Red Alert).

### 3.2. Luồng cảnh báo khẩn cấp (Emergency Flow)
- **Kịch bản A: Bỏ thuốc liên tiếp >= 3 lần**
  - Gửi thông báo khẩn cấp đến người chăm sóc (Zalo/SMS).
  - Hiển thị cảnh báo đỏ nổi bật trên Dashboard của Bác sĩ.
- **Kịch bản B: Phát hiện tác dụng phụ nguy hiểm (qua Daily Survey hoặc SOS)**
  - Khi bệnh nhân báo cáo triệu chứng nhóm Nguy cấp (khó thở, đau ngực dữ dội, chóng mặt mất thăng bằng, phát ban toàn thân):
    1. Hiển thị ngay chỉ dẫn sơ cứu khẩn cấp dạng thẻ trực quan (từ nguồn y khoa chính thống).
    2. Kích hoạt cuộc gọi/tin nhắn SMS khẩn cấp tới người chăm sóc.
    3. Đẩy thông báo khẩn cấp (WebSocket/SSE) lên Portal của Bác sĩ điều trị.
    4. Cung cấp nút gọi nhanh 115 hoặc số điện thoại bác sĩ/bệnh viện gần nhất.

---

## 4. Kiến trúc kỹ thuật dự kiến

| Thành phần | Công nghệ đề xuất | Vai trò / Lý do lựa chọn |
|---|---|---|
| **Frontend** | React / Next.js + TailwindCSS + PWA (Service Workers) | Hỗ trợ PWA để cài đặt như App điện thoại, chạy offline và gửi Web Push. |
| **Backend API** | FastAPI / Python | Hiệu năng cao, tích hợp mượt mượt với các thư viện AI/Python. |
| **Database** | PostgreSQL | Lưu trữ dữ liệu quan hệ (đơn thuốc, người dùng, log tuân thủ). |
| **Vector Database**| ChromaDB / PGVector | Lưu trữ và tìm kiếm thông tin tương tác thuốc, tác dụng phụ (RAG). |
| **Task Queue** | Celery + Redis | Xử lý các tác vụ ngầm: lên lịch gửi thông báo, kiểm tra bỏ thuốc tự động. |
| **AI Orchestrator**| LangGraph | Xây dựng các Agent (Planning Agent, Rescheduling Agent, Survey Agent) với sơ đồ trạng thái kiểm soát chặt chẽ. |
| **OCR Service** | EasyOCR / PaddleOCR hoặc Cloud API | Nhận diện văn bản đơn thuốc từ ảnh chụp. |
| **Kênh thông báo** | Firebase Cloud Messaging (FCM) + Zalo/SMS Twilio API | Đảm bảo tin nhắn cảnh báo đến đích nhanh nhất. |

---

## 5. Các KPI đánh giá MVP thành công

- **Tỷ lệ tuân thủ trung bình của bệnh nhân dùng app:** Đạt từ **75%** trở lên sau 4 tuần sử dụng.
- **Độ chính xác của AI OCR (sau khi sửa đổi thủ công):** Đạt **100%** thông tin đơn thuốc chính xác đi vào hệ thống (bắt buộc qua khâu bác sĩ duyệt).
- **Thời gian trễ cảnh báo SOS:** Dưới **10 giây** để đẩy thông báo lên Dashboard bác sĩ và gửi SMS/Zalo cho người thân.
- **Độ hài lòng về trải nghiệm người cao tuổi (CSAT):** Đạt trên **4/5 điểm** qua khảo sát giao diện tối giản.

---

## 6. Đánh giá Rủi ro & Giải pháp hạn chế (Risk & Mitigation)

1. **Rủi ro AI tự ý đưa ra lời khuyên y khoa sai lệch (Hallucination):**
   - *Giải pháp:* Sử dụng Prompt Guardrails nghiêm ngặt và RAG chỉ truy xuất từ nguồn tài liệu y khoa được kiểm duyệt (như Dược thư Quốc gia). Cấm AI chẩn đoán bệnh mới; chỉ ghi nhận triệu chứng và hướng dẫn sơ cứu cơ bản theo quy trình có sẵn.
2. **Bệnh nhân mất kết nối mạng:**
   - *Giải pháp:* Thiết lập cơ chế PWA Offline. Đồng bộ hóa lịch uống thuốc xuống bộ nhớ thiết bị. Lời nhắc vẫn hoạt động nhờ Service Worker cục bộ. Ghi log ngoại tuyến và gửi lên server khi có mạng trở lại.
3. **Người cao tuổi không phản hồi nhắc nhở:**
   - *Giải pháp:* Nếu sau 15 phút không có tương tác trên ứng dụng, hệ thống tự động gửi tin nhắn SMS/Zalo hoặc gọi cuộc gọi tự động (Robocall) nhắc nhở. Sau 30 phút không phản hồi sẽ báo cho người chăm sóc.
4. **Nhận diện sai tên thuốc qua OCR:**
   - *Giải pháp:* Kết hợp thuật toán so khớp chuỗi mờ (fuzzy matching) với danh mục thuốc y tế chuẩn. Bắt buộc hiển thị giao diện đối chiếu song song giữa ảnh chụp gốc và kết quả OCR để người dùng (Bác sĩ/Bệnh nhân) chỉnh sửa trước khi lưu đơn.
