# Phân tích nội dung Drive — AdhereMind

## Tổng quan

Thư mục Drive **“AI thực chiến SU 2026”** chứa 7 tệp về dự án **AdhereMind — Web-App hỗ trợ tuân thủ điều trị cho người cao tuổi**.

## 1. Bài toán và ý tưởng

Dự án giải quyết các vấn đề thường gặp ở bệnh nhân cao tuổi và bệnh nhân mắc bệnh mạn tính:

- Quên uống thuốc hoặc uống sai giờ.
- Tự ý bỏ thuốc khi thấy khỏe hơn.
- Khó duy trì lịch sinh hoạt và điều trị.
- Thiếu kênh liên lạc liên tục với bác sĩ và người thân.
- Phát hiện muộn các biến cố hoặc tác dụng phụ.

AdhereMind là Web-App/PWA kết nối ba nhóm người dùng: bác sĩ điều trị, bệnh nhân và người thân/người chăm sóc.

## 2. Các chức năng MVP

- Bác sĩ đăng nhập tài khoản chuyên môn.
- Nhập đơn thuốc điện tử dạng JSON chuẩn hóa.
- Dashboard theo dõi bệnh nhân và tỷ lệ tuân thủ.
- Bệnh nhân đăng nhập bằng số điện thoại và OTP.
- Cấu hình giờ sinh hoạt cá nhân.
- Tự động lập lịch uống thuốc bằng Planning Agent.
- Nhắc uống thuốc qua Web Push.
- Ghi nhận trạng thái: đã uống, uống muộn hoặc bỏ qua.
- Ghi log trạng thái uống thuốc.
- Rescheduling Agent tự điều chỉnh lịch khi bệnh nhân uống muộn hoặc bỏ liều.
- Chụp đơn thuốc bằng OCR/RAG và xác nhận thông tin.
- Khảo sát sức khỏe hằng ngày.
- Nút SOS trong tình huống khẩn cấp.
- Cảnh báo người thân qua SMS/Zalo và bác sĩ trên Portal.

## 3. Luồng cảnh báo khẩn cấp

### Bỏ thuốc quá 3 lần

Hệ thống phát hiện trạng thái “Bỏ qua” hoặc không phản hồi, gửi thông báo cho người thân và đánh dấu bệnh nhân bằng cảnh báo màu đỏ trên dashboard bác sĩ.

### Tác dụng phụ bất thường

Khi bệnh nhân khai báo khó thở, phát ban, đau ngực, chóng mặt hoặc triệu chứng tương tự, hệ thống:

1. Hiển thị hướng dẫn sơ cứu.
2. Gọi hoặc nhắn cho người thân.
3. Hiển thị cảnh báo trên Portal bác sĩ.

AI chỉ hỗ trợ lập lịch và thu thập thông tin; không tự chẩn đoán hoặc tự thay đổi thuốc.

## 4. Kiến trúc kỹ thuật dự kiến

| Thành phần | Công nghệ |
|---|---|
| Frontend | React + PWA |
| Backend API | FastAPI/Python |
| Task queue | Celery + Redis |
| AI Agent | LangGraph |
| RAG/Knowledge | Cơ sở dữ liệu thông tin thuốc |
| OCR | PaddleOCR hoặc VietOCR |
| Database | PostgreSQL |
| Thông báo | Web Push + SMS/Zalo API |

Các agent chính gồm Planning Agent, Rescheduling Agent và Daily Health Survey. Agent khảo sát chỉ thu thập triệu chứng, không chẩn đoán.

## 5. KPI của MVP

- Tỷ lệ tuân thủ trung bình: **từ 70% trở lên**.
- Thời gian phản hồi nhắc nhở: **dưới 30 phút**.
- Tỷ lệ cảnh báo Red Alert chính xác: **từ 90% trở lên**.

## 6. Wireframe

- [Wireframe bệnh nhân](https://drive.google.com/file/d/1QxlaNZlqjYogOyh1HgFYJEB2zP60DLnh/view): đăng nhập OTP, cấu hình lịch sinh hoạt, xem lịch uống thuốc và nút SOS.
- [Wireframe tương tác và giám sát](https://drive.google.com/file/d/1CRNCLZfTYmGgsd10r_41u1h3Ujbhh588/view): nhắc uống thuốc, chọn trạng thái uống, khảo sát sức khỏe và chụp/xác nhận đơn thuốc bằng OCR/RAG.
- [Wireframe cảnh báo bác sĩ](https://drive.google.com/file/d/1Y54rWkamiYB9WTdTDsCMRXNH9cOy2HJE/view): màn hình cảnh báo khẩn cấp cho bệnh nhân và dashboard bác sĩ.

## 7. Đánh giá

### Điểm mạnh

- Bài toán thực tế và dễ trình bày trong Demo Day.
- Luồng người dùng rõ ràng giữa bác sĩ, bệnh nhân và người thân.
- Có AI Agent nhưng vẫn đặt giới hạn an toàn.
- Wireframe thống nhất với PRD và đặc tả MVP.
- Có Human-in-the-Loop: đơn thuốc phải do bác sĩ tạo và duyệt.

### Rủi ro cần xử lý

- Cần tích hợp thật SMS/Zalo, Web Push và OTP nếu muốn demo hoàn chỉnh.
- OCR đơn thuốc có thể nhận dạng sai, nên bắt buộc có bước xác nhận.
- Không để AI tự thay đổi liều lượng hoặc tư vấn y khoa.
- Phải phân quyền và bảo vệ dữ liệu sức khỏe cá nhân.
- Cần định nghĩa rõ “uống muộn”, “bỏ qua” và xử lý khi mất mạng.
- Cần kiểm thử cảnh báo giả, cảnh báo trễ và các tình huống khẩn cấp.

## 8. Danh sách tài liệu

- [Brief dự án](https://drive.google.com/file/d/1WeP8A5mksgwhnRPYD69KoGKjE3ba1-Fl/view)
- [PRD v2](https://drive.google.com/file/d/1YQQVb_7c3wpwxgFzhtjJK9Ms46Xo9c5_/view)
- [Đặc tả tính năng MVP v2](https://drive.google.com/file/d/1x6ck5mxcocmVtghajS-mbu336W5cjGCR/view)
- [Tài liệu GitHub AI Log Setup](https://drive.google.com/file/d/1xGIrp_Yt06mKweqlL12j9oV1nNPA-3YT/view)
- Ba wireframe được liệt kê trong mục 6.

## Kết luận

Drive cung cấp bộ hồ sơ sản phẩm tương đối hoàn chỉnh: brief, PRD, đặc tả MVP, wireframe và tài liệu AI logging. AdhereMind đã có nền tảng tốt để triển khai; các ưu tiên tiếp theo là chuẩn hóa API, dữ liệu đơn thuốc, trạng thái nhắc thuốc và cơ chế cảnh báo an toàn.
