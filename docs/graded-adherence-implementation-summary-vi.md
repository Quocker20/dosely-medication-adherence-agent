# Tóm tắt kế hoạch triển khai — Cảnh báo tuân thủ theo cấp độ

## Tổng quan
Chia làm 7 giai đoạn, xây theo thứ tự để giai đoạn 1–4 và 7 đã tạo ra một hệ
thống cảnh báo phân cấp hoạt động đầy đủ **mà chưa cần AI**. Nếu về sau quyết
định bỏ bước LLM, không có phần nào bị lãng phí.

## Phát hiện trước khi code
- **Cây migration hiện đang bị chẻ hai nhánh** (`0016_seed_medications` và
  `0019_user_need_onboarding` cùng rẽ từ `0015`) — lỗi có sẵn từ trước, không
  phải do tính năng này gây ra, nhưng phải merge lại đầu tiên vì mọi migration
  sau đều bị chặn bởi lỗi này.

## 7 giai đoạn

**1. Database** — thêm cột `is_critical` (đánh dấu thuốc nguy hiểm) trên đơn
thuốc và trên từng liều đã lên lịch; tạo bảng `adherence_reviews` lưu lịch sử
đánh giá mỗi đêm; mở rộng danh sách loại cảnh báo để nhận diện cảnh báo từ tính
năng mới. Toàn bộ dùng kỹ thuật migration không khoá bảng khi thêm cột/chỉ mục
trên bảng lớn.

**2. Đường dẫn khẩn cấp** — bác sĩ đánh dấu thuốc nguy hiểm ngay trên đơn; hệ
thống quét mỗi 15 phút (đã có sẵn) được thu hẹp lại: chỉ báo đỏ ngay lập tức
khi bệnh nhân bỏ lỡ 3 liều liên tiếp của thuốc được đánh dấu, thay vì báo đỏ
cho mọi loại thuốc như hiện tại.

**3. Tính chỉ số** — mỗi đêm tính hàng loạt (không phải tính từng bệnh nhân
một, tránh làm chậm hệ thống) các chỉ số: tỷ lệ tuân thủ, xu hướng so với tuần
trước, tỷ lệ bỏ lỡ theo khung giờ, theo từng loại thuốc, và đối chiếu với
khảo sát sức khoẻ gần đây.

**4. Luật xếp hạng mức độ nghiêm trọng** — thuần code, không AI. Xếp bệnh nhân
vào 1 trong 4 mức: Không vấn đề / Nhẹ / Vừa / Nặng, dựa trên ngưỡng tỷ lệ %
(đã dùng chung ngưỡng đang hiển thị trên dashboard bác sĩ để số liệu nhất
quán). Có cơ chế leo thang: nếu tình trạng không cải thiện sau vài ngày, mức độ
cảnh báo tự tăng dần.

**5. Bước AI** — chỉ chạy cho bệnh nhân đã bị luật ở bước 4 đánh giá có vấn đề.
AI chỉ được chọn 1 trong 6 nguyên nhân có sẵn (lệch giờ uống, nghi tác dụng
phụ, cố tình bỏ thuốc, mất kết nối/không tương tác, gián đoạn bên ngoài, hoặc
"chưa rõ") và viết giải thích ngắn cho bác sĩ — **không được thay đổi mức độ
nghiêm trọng đã được luật quyết định**. Nếu AI lỗi hoặc timeout, hệ thống vẫn
thực hiện đúng hành động mà luật đã quyết, chỉ thiếu phần giải thích.

**6. Job chạy đêm và gửi thông báo** — chạy 5h sáng mỗi ngày (để dữ liệu ngày
hôm trước đã chốt, và bác sĩ thấy cảnh báo ngay đầu ca làm việc). Thông báo gửi
bệnh nhân bị giữ lại, chỉ gửi trong khung giờ ban ngày (8h–20h), không bao giờ
gửi lúc nửa đêm. Có giới hạn số lượt gọi AI mỗi đêm để kiểm soát chi phí.

**7. Sửa thứ tự danh sách bệnh nhân trên dashboard** — để cảnh báo mức "Cảnh
báo nhẹ" mới không che lấp các ca thật sự khẩn cấp (đỏ) khi bác sĩ mở dashboard.

## Rủi ro kỹ thuật đã kiểm soát
- **Tránh quét toàn bảng**: thêm chỉ mục mới cho truy vấn quét toàn bộ bệnh
  nhân mỗi đêm — nếu không sẽ ngày càng chậm khi dữ liệu tăng.
- **Tránh N+1 (tính từng bệnh nhân một)**: toàn bộ bước tính chỉ số dùng 6 câu
  truy vấn duy nhất cho toàn bộ bệnh nhân, không có vòng lặp gọi database theo
  từng người.
- **Tránh race condition**: dùng ràng buộc `UNIQUE` để nếu job chạy trùng 2
  lần trong đêm (do lỗi hệ thống) sẽ tự chặn thay vì tạo cảnh báo trùng lặp.
- **Không đưa văn bản tự do của bệnh nhân (mô tả triệu chứng) vào AI** ở giai
  đoạn 1 — chỉ dùng mã triệu chứng và mức độ nghiêm trọng đã được chuẩn hoá,
  để tránh rủi ro chèn lệnh độc hại (prompt injection) qua văn bản bệnh nhân
  nhập.

## Kiểm thử
Mỗi giai đoạn có bộ test riêng: luật xếp hạng, cơ chế leo thang (bao gồm
trường hợp job bị bỏ lỡ một đêm), độ chính xác câu truy vấn, và cả một bài test
xác nhận thay đổi hành vi cố ý ở bước quét khẩn cấp (lọc chỉ thuốc nguy hiểm).

## Thời gian dự kiến
Khoảng 2 tuần với 1 kỹ sư backend, giả định không đổi logic đơn thuốc/lịch
uống hiện có (tính năng chỉ đọc dữ liệu đó, không ghi đè).
