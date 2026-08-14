# ĐẶC TẢ CHI TIẾT CÁC PYDANTIC SCHEMAS (FASTAPI BLUEPRINT) - REMINDRX

Tài liệu này định nghĩa cấu trúc chi tiết toàn bộ các Pydantic Schemas phục vụ việc trao đổi dữ liệu qua hệ thống REST API của dự án **RemindRx**. Các cấu trúc dữ liệu dưới đây phản ánh chính xác 21 bảng PostgreSQL Database Schema và hợp đồng giao tiếp trong `api-contract.md`, được thiết kế tối ưu theo chuẩn **FastAPI (Python)** naming convention.

---

## CẤU TRÚC PHÂN TRANG CHUNG (COMMON PAGINATION BUNDLE)

### PageResponse
* **Mục đích**: Schema bọc ngoài (Wrapper Schema) chuẩn hóa cho toàn bộ các API truy vấn danh sách có phân trang nhằm thống nhất cấu trúc dữ liệu trả về cho Frontend.
* **Module**: `src.common.schemas`
* **Cấu trúc thuộc tính**:
  * `content` (List[Any]): Mảng chứa danh sách các phần tử kết quả của trang hiện tại.
  * `page_no` (int): Chỉ mục của trang hiện tại (Bắt đầu từ `0` hoặc `1` tùy quy ước Client).
  * `page_size` (int): Số lượng phần tử tối đa trên một trang.
  * `total_elements` (int): Tổng số lượng phần tử tìm thấy trong cơ sở dữ liệu.
  * `total_pages` (int): Tổng số lượng trang khả dụng.
  * `last` (bool): Cờ đánh dấu đây có phải là trang cuối cùng hay không.

---

## PHÂN HỆ 1: XÁC THỰC & NGƯỜI DÙNG (AUTHENTICATION & USER)

### 1.1 LoginRequest
* **Mục đích**: Tiếp nhận số điện thoại và mật khẩu PIN 6 chữ số để đăng nhập tài khoản.
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `phone` (str, Field pattern=r'^\+?[0-9]{9,15}$'): Số điện thoại đăng nhập chuẩn quốc tế.
  * `password` (str, Field min_length=6, max_length=6, pattern=r'^\d{6}$'): Mật khẩu mã PIN 6 chữ số.

### 1.2 ChangePasswordRequest
* **Mục đích**: Tiếp nhận mật khẩu PIN hiện tại và mật khẩu PIN mới để thay đổi mật khẩu (bắt buộc cho lần đầu đăng nhập hoặc thay đổi chủ động).
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `current_password` (str, Field min_length=6, max_length=6, pattern=r'^\d{6}$'): Mật khẩu PIN hiện tại.
  * `new_password` (str, Field min_length=6, max_length=6, pattern=r'^\d{6}$'): Mật khẩu PIN mới 6 chữ số.

### 1.3 AuthTokenResponse
* **Mục đích**: Trả về cặp Token JWT và cờ trạng thái đăng nhập lần đầu sau khi xác thực thành công.
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `access_token` (str): Mã JWT dùng cho các request API bảo mật (Thời hạn ngắn).
  * `refresh_token` (str): Mã dùng để cấp lại Access Token mới.
  * `token_type` (str): Định dạng token (Mặc định: `"Bearer"`).
  * `expires_in` (int): Thời gian sống của Access Token (tính bằng giây).
  * `is_first_login` (bool): Cờ báo `True` nếu đây là lần đầu đăng nhập (yêu cầu điều hướng tới màn hình đổi mật khẩu).
  * `user` (UserResponse): Đối tượng thông tin tổng quan của tài khoản.

### 1.4 UserResponse
* **Mục đích**: Trả về thông tin cốt lõi của tài khoản từ bảng `users`.
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã định danh tài khoản.
  * `phone` (str): Số điện thoại duy nhất.
  * `role` (str): Vai trò người dùng (Enum: `PATIENT`, `DOCTOR`, `ADMIN`, `CAREGIVER`).
  * `status` (str): Trạng thái tài khoản (Enum: `ACTIVE`, `INACTIVE`, `BLOCKED`).

### 1.5 RefreshTokenRequest
* **Mục đích**: Tiếp nhận Refresh Token để gia hạn phiên làm việc.
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `refresh_token` (str): Chuỗi Refresh Token hợp lệ.

### 1.6 LogoutRequest
* **Mục đích**: Tiếp nhận token cần vô hiệu hóa khi người dùng đăng xuất.
* **Module**: `src.modules.auth.schemas`
* **Cấu trúc thuộc tính**:
  * `refresh_token` (str): Chuỗi Refresh Token cần đưa vào Blacklist.

### 1.7 MessageResponse
* **Mục đích**: Schema phản hồi thông điệp kết quả cho các thao tác đơn giản (Xóa, Logout, Hủy...).
* **Module**: `src.common.schemas`
* **Cấu trúc thuộc tính**:
  * `message` (str): Nội dung thông báo kết quả.

---

## PHÂN HỆ 2: QUẢN LÝ BÁC SĨ & LOGS (ADMIN DOCTOR MANAGEMENT & AUDIT)

### 2.1 CreateDoctorRequest
* **Mục đích**: Admin khởi tạo tài khoản Bác sĩ mới trên hệ thống.
* **Module**: `src.modules.admin.schemas`
* **Cấu trúc thuộc tính**:
  * `phone` (str, Field pattern=r'^\+?[0-9]{9,15}$'): Số điện thoại bác sĩ.
  * `name` (str, Field max_length=255): Họ và tên bác sĩ.
  * `license_no` (str, Field max_length=100): Số chứng chỉ hành nghề y khoa (Unique).
  * `specialty` (Optional[str], Field max_length=150): Chuyên khoa phụ trách.

### 2.2 UpdateDoctorRequest
* **Mục đích**: Admin cập nhật thông tin chứng chỉ, chuyên khoa hoặc trạng thái hoạt động của Bác sĩ.
* **Module**: `src.modules.admin.schemas`
* **Cấu trúc thuộc tính**:
  * `name` (Optional[str], Field max_length=255): Họ và tên mới.
  * `specialty` (Optional[str], Field max_length=150): Chuyên khoa mới.
  * `status` (Optional[str], Field pattern=r'^(ACTIVE|INACTIVE)$'): Trạng thái tài khoản (`ACTIVE`/`INACTIVE`).

### 2.3 DoctorDetailResponse
* **Mục đích**: Phản hồi hồ sơ chi tiết của Bác sĩ ghép từ `users` và `doctor_profiles`. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[DoctorDetailResponse]`.
* **Module**: `src.modules.admin.schemas`
* **Cấu trúc thuộc tính**:
  * `user_id` (UUID): Khóa chính tài khoản bác sĩ.
  * `phone` (str): Số điện thoại liên hệ.
  * `role` (str): Mặc định `"DOCTOR"`.
  * `status` (str): Trạng thái tài khoản.
  * `name` (str): Họ tên bác sĩ.
  * `license_no` (str): Số chứng chỉ hành nghề.
  * `specialty` (Optional[str]): Chuyên khoa.
  * `created_at` (datetime): Mốc thời gian tạo tài khoản.

### 2.4 AuditLogListResponse
* **Mục đích**: Phản hồi từng item trong nhật ký kiểm toán hệ thống từ bảng `audit_logs` phục vụ Admin phân trang `PageResponse[AuditLogListResponse]`.
* **Module**: `src.modules.admin.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã log kiểm toán.
  * `actor_user_id` (Optional[UUID]): Mã người thực hiện thao tác.
  * `action` (str): Tên hành động (Ví dụ: `"APPROVE_PRESCRIPTION"`, `"CREATE_DOCTOR"`).
  * `entity_type` (str): Loại đối tượng tác động (`PRESCRIPTION`, `DOCTOR_PROFILE`).
  * `entity_id` (Optional[UUID]): Mã đối tượng chịu tác động.
  * `old_values` (Optional[Dict[str, Any]]): Giá trị dữ liệu trước thao tác.
  * `new_values` (Optional[Dict[str, Any]]): Giá trị dữ liệu sau thao tác.
  * `ip_address` (Optional[str]): Địa chỉ IP người thực hiện.
  * `created_at` (datetime): Thời điểm ghi nhận.

### 2.5 CreateDoctorResponse
* **Mục đích**: Phản hồi khởi tạo tài khoản Bác sĩ thành công bao gồm thông tin chi tiết Bác sĩ và mật khẩu PIN tạm thời (hiển thị 1 lần).
* **Module**: `src.modules.admin.schemas`
* **Cấu trúc thuộc tính**:
  * `doctor` (DoctorDetailResponse): Hồ sơ chi tiết bác sĩ.
  * `temp_password` (str): Mật khẩu PIN 6 chữ số ngẫu nhiên cấp lần đầu.

---

## PHÂN HỆ 3: QUẢN LÝ BỆNH NHÂN & THUỐC (DOCTOR & PATIENT CLINICAL MANAGEMENT)

### 3.1 CreatePatientByDoctorRequest
* **Mục đích**: Bác sĩ chủ động tạo nhanh hồ sơ Bệnh nhân tại cơ sở y tế.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `phone` (str): Số điện thoại bệnh nhân.
  * `name` (str, Field max_length=255): Họ và tên bệnh nhân.
  * `dob` (Optional[date]): Ngày tháng năm sinh (`YYYY-MM-DD`).
  * `sex` (Optional[str]): Giới tính (`MALE`, `FEMALE`, `OTHER`).
  * `timezone` (str, default="Asia/Ho_Chi_Minh"): Múi giờ sinh hoạt của bệnh nhân.
  * `emergency_note` (Optional[str]): Ghi chú y tế khẩn cấp/tiền sử dị ứng.

### 3.2 PatientDetailResponse
* **Mục đích**: Phản hồi thông tin hồ sơ chi tiết của Bệnh nhân từ bảng `patient_profiles`. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[PatientDetailResponse]`.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `user_id` (UUID): Khóa chính mã bệnh nhân.
  * `phone` (str): Số điện thoại liên hệ.
  * `role` (str): Mặc định `"PATIENT"`.
  * `status` (str): Trạng thái tài khoản.
  * `name` (str): Họ tên bệnh nhân.
  * `dob` (Optional[date]): Ngày sinh.
  * `sex` (Optional[str]): Giới tính.
  * `timezone` (str): Múi giờ.
  * `privacy_consent_status` (Optional[str]): Trạng thái đồng ý chia sẻ dữ liệu y tế.
  * `emergency_note` (Optional[str]): Ghi chú khẩn cấp.
  * `created_at` (datetime): Thời điểm khởi tạo.
  * `updated_at` (datetime): Thời điểm cập nhật gần nhất.

---

## PHÂN HỆ 4: LỊCH SINH HOẠT & NGƯỜI THÂN (ROUTINE & CAREGIVERS)

### 4.1 PatientOnboardingRequest
* **Mục đích**: Bệnh nhân thiết lập thông tin cá nhân và Khung giờ sinh hoạt bắt buộc ở lần đăng nhập đầu tiên.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `name` (str): Họ và tên bệnh nhân.
  * `dob` (Optional[date]): Ngày sinh.
  * `sex` (Optional[str]): Giới tính.
  * `timezone` (str, default="Asia/Ho_Chi_Minh"): Múi giờ.
  * `emergency_note` (Optional[str]): Ghi chú khẩn cấp.
  * `routine` (UpdateRoutineRequest): Đối tượng nhúng chứa thông tin các mốc giờ sinh hoạt.

### 4.2 UpdateRoutineRequest
* **Mục đích**: Tiếp nhận hoặc cập nhật các mốc giờ sinh hoạt chính trong ngày từ bảng `patient_routines`.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `wake_time` (Optional[time]): Giờ thức dậy (`HH:MM:SS`).
  * `breakfast_time` (Optional[time]): Giờ ăn sáng.
  * `lunch_time` (Optional[time]): Giờ ăn trưa.
  * `dinner_time` (Optional[time]): Giờ ăn tối.
  * `sleep_time` (Optional[time]): Giờ đi ngủ.

### 4.3 PatientRoutineResponse
* **Mục đích**: Phản hồi dữ liệu khung giờ sinh hoạt hiện hành của bệnh nhân.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã định danh bản ghi routine.
  * `patient_id` (UUID): Mã bệnh nhân tương ứng.
  * `wake_time` (Optional[time]): Giờ thức dậy.
  * `breakfast_time` (Optional[time]): Giờ ăn sáng.
  * `lunch_time` (Optional[time]): Giờ ăn trưa.
  * `dinner_time` (Optional[time]): Giờ ăn tối.
  * `sleep_time` (Optional[time]): Giờ đi ngủ.
  * `updated_at` (datetime): Thời điểm cập nhật mốc giờ.

### 4.4 PatientProfileDetailResponse
* **Mục đích**: Trả về tổng hợp hồ sơ cá nhân kèm lịch sinh hoạt sau bước Onboarding.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `profile` (PatientDetailResponse): Đối tượng hồ sơ bệnh nhân.
  * `routine` (PatientRoutineResponse): Đối tượng lịch sinh hoạt.

### 4.5 CreateCaregiverLinkRequest
* **Mục đích**: Liên kết một tài khoản Người thân để nhận thông báo theo dõi bệnh nhân từ bảng `caregiver_links`.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `caregiver_phone` (str): Số điện thoại của người thân.
  * `relationship` (Optional[str]): Mối quan hệ (Ví dụ: `"Con gái"`, `"Vợ"`, `"Chồng"`).
  * `channels` (List[str], default=["APP_NOTIFICATION"]): Các kênh nhận thông báo (Mảng JSON: `["SMS", "ZALO", "APP_NOTIFICATION"]`).

### 4.6 CaregiverLinkDetailResponse
* **Mục đích**: Phản hồi thông tin liên kết người thân hoàn chỉnh.
* **Module**: `src.modules.patients.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã định danh bản ghi liên kết.
  * `patient_id` (UUID): Mã bệnh nhân.
  * `caregiver_user_id` (UUID): Mã tài khoản người thân trong bảng `users`.
  * `relationship` (Optional[str]): Mối quan hệ gia đình.
  * `channels` (List[str]): Danh sách kênh thông báo.
  * `status` (str): Trạng thái liên kết (`ACTIVE`/`INACTIVE`).
  * `created_at` (datetime): Thời điểm tạo liên kết.

---

## PHÂN HỆ 5: DANH MỤC THUỐC & ĐƠN THUỐC (MEDICATIONS & PRESCRIPTIONS)

### 5.1 MedicationDetailResponse
* **Mục đích**: Phản hồi chi tiết thông tin một loại thuốc tra cứu từ bảng `medications`. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[MedicationDetailResponse]`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã định danh thuốc.
  * `name` (str): Tên thương mại của thuốc.
  * `composition` (Optional[str]): Thành phần hoạt chất.
  * `manufacturer` (Optional[str]): Nhà sản xuất.
  * `uses` (Optional[str]): Công dụng/Chỉ định.
  * `side_effects` (Optional[str]): Tác dụng phụ cần lưu ý.
  * `image_url` (Optional[str]): Đường dẫn ảnh mẫu vỏ thuốc.
  * `source_name` (str): Nguồn dữ liệu dược thư.
  * `is_active` (bool): Trạng thái khả dụng trong danh mục.

### 5.2 CreatePrescriptionRequest
* **Mục đích**: Bác sĩ tạo Đơn thuốc nháp (`DRAFT`) mới cho bệnh nhân trong một request duy nhất (atomic), gồm cả danh sách cữ thuốc (`items`). Endpoint: `POST /prescriptions`.
* **Logic Find-or-Create bệnh nhân**: Bác sĩ chỉ nhập số điện thoại bệnh nhân (plaintext, không cần biết `patient_id` trước). Service tra `users.phone`:
  * Nếu **đã tồn tại**: dùng `user_id` hiện có làm `patient_id` của đơn thuốc.
  * Nếu **chưa tồn tại**: tạo mới `User` (role=`PATIENT`) + `PatientProfile` ngay trong cùng transaction. Mọi cột NOT NULL không có default (ví dụ `patient_profiles.name`) được điền literal chuỗi `"NULL"` làm placeholder — bệnh nhân tự cập nhật hồ sơ thật khi Onboarding (`POST /patients/me/profile`). Cột có server default (`timezone`) dùng default, không cần điền. Mật khẩu PIN 6 chữ số tạm thời được sinh ngẫu nhiên như luồng `CreateDoctorRequest`/`CreatePatientByDoctorRequest`, trả về một lần trong `CreatePrescriptionResponse.temp_password`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `phone` (str, Field pattern=r'^\+?[0-9]{9,15}$'): Số điện thoại bệnh nhân (plaintext) dùng để tìm hoặc tạo tài khoản.
  * `diagnosis_note` (Optional[str]): Chẩn đoán lâm sàng của bác sĩ (Ví dụ: Mã ICD-10 và mô tả bệnh).
  * `items` (List[CreatePrescriptionItemRequest], default=[]): Danh sách cữ thuốc tạo kèm ngay trong đơn. Có thể để trống và bổ sung sau qua `POST /prescriptions/{prescription_id}/items` (chỉ khi đơn còn `DRAFT`).

### 5.3 UpdatePrescriptionRequest
* **Mục đích**: Bác sĩ cập nhật chẩn đoán cho Đơn thuốc còn ở trạng thái `DRAFT`. Endpoint: `PUT /prescriptions/{prescription_id}`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `diagnosis_note` (Optional[str]): Chẩn đoán lâm sàng của bác sĩ.

### 5.4 CreatePrescriptionResponse
* **Mục đích**: Phản hồi cho `POST /prescriptions`. Bọc ngoài `PrescriptionDetailResponse` kèm mật khẩu PIN tạm thời — chỉ khác `null` khi request vừa provision tài khoản bệnh nhân mới (phone chưa tồn tại), tương tự deviation đã áp dụng ở `CreatePatientResponse`/`CaregiverLinkDetailResponse`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `prescription` (PrescriptionDetailResponse): Đơn thuốc vừa tạo, gồm `items`.
  * `temp_password` (Optional[str]): Mật khẩu PIN 6 chữ số ngẫu nhiên cấp lần đầu cho bệnh nhân mới. `null` nếu bệnh nhân đã tồn tại từ trước.

### 5.5 CancelPrescriptionRequest
* **Mục đích**: Bác sĩ gửi lý do khi tiến hành Hủy đơn thuốc (`CANCELLED`).
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `cancel_reason` (str, Field min_length=1): Lý do hủy đơn thuốc.

### 5.6 CreatePrescriptionItemRequest / UpdatePrescriptionItemRequest
* **Mục đích**: Tiếp nhận thông tin liều lượng và cách dùng cho một cữ thuốc trong bảng `prescription_items`.
* **Logic display_name (snapshot, không FK)**: Client không gửi `display_name`. Service tra `medication_id` trong danh mục `medications`, lấy `Medication.name` và đóng băng (freeze) giá trị đó vào cột `prescription_items.display_name` ngay tại thời điểm ghi — không tồn tại lại ràng buộc FK giữa `prescription_items.medication_id` và `medications.id` (đã drop ở migration `0007_drop_pi_med_fk`), nên record giữ nguyên tên thuốc kể cả khi sau này `Medication` bị sửa hoặc xoá. `medication_id` không hợp lệ (không tồn tại trong `medications`) trả về `404 Not Found`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `medication_id` (UUID, bắt buộc): Mã thuốc trong danh mục `medications` dùng để tra `display_name` tại thời điểm ghi. Không phải khoá ngoại (no FK) — chỉ là con trỏ lịch sử.
  * `dose_unit` (str): Đơn vị liều dùng (Ví dụ: `"VIEN"`, `"GOI"`, `"ML"`).
  * `morning_dose` (Optional[float]): Liều uống buổi sáng.
  * `noon_dose` (Optional[float]): Liều uống buổi trưa.
  * `evening_dose` (Optional[float]): Liều uống buổi chiều/tối.
  * `bedtime_dose` (Optional[float]): Liều uống trước khi đi ngủ.
  * `route` (str, default="ORAL"): Đường dùng thuốc (`ORAL`, `INJECTION`, `TOPICAL`...).
  * `meal_relation` (Optional[str]): Quan hệ với bữa ăn (`BEFORE_MEAL`, `AFTER_MEAL`, `WITH_MEAL`).
  * `minimum_interval_minutes` (Optional[int]): Khoảng cách tối thiểu giữa 2 cữ uống (tính bằng phút).
  * `start_date` (date): Ngày bắt đầu uống.
  * `end_date` (Optional[date]): Ngày kết thúc đợt uống.
  * `instructions` (Optional[str]): Hướng dẫn chi tiết bổ sung.

### 5.7 PrescriptionItemDetailResponse
* **Mục đích**: Phản hồi thông tin chi tiết một dòng thuốc thuộc đơn.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã định danh item đơn thuốc.
  * `prescription_id` (UUID): Mã đơn thuốc cha.
  * `medication_id` (Optional[UUID]): Mã thuốc danh mục dùng để tra tên tại thời điểm ghi (không FK).
  * `display_name` (str): Tên thuốc hiển thị — snapshot đóng băng từ `Medication.name`, không đổi dù danh mục thay đổi sau đó.
  * `dose_unit` (str): Đơn vị liều.
  * `morning_dose` (Optional[float]): Liều sáng.
  * `noon_dose` (Optional[float]): Liều trưa.
  * `evening_dose` (Optional[float]): Liều chiều.
  * `bedtime_dose` (Optional[float]): Liều tối.
  * `route` (str): Đường dùng.
  * `meal_relation` (Optional[str]): Lịch uống theo bữa ăn.
  * `minimum_interval_minutes` (Optional[int]): Khoảng cách cữ.
  * `start_date` (date): Ngày bắt đầu.
  * `end_date` (Optional[date]): Ngày kết thúc.
  * `instructions` (Optional[str]): Hướng dẫn dùng.
  * `created_at` (datetime): Thời điểm tạo.

### 5.8 PrescriptionDetailResponse
* **Mục đích**: Phản hồi dữ liệu đơn thuốc hoàn chỉnh bao gồm danh sách các cữ thuốc chi tiết bên trong. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[PrescriptionDetailResponse]`.
* **Module**: `src.modules.prescriptions.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã đơn thuốc.
  * `patient_id` (UUID): Mã bệnh nhân.
  * `doctor_id` (Optional[UUID]): Mã bác sĩ kê đơn.
  * `status` (str): Trạng thái đơn (`DRAFT`, `APPROVED`, `CANCELLED`).
  * `diagnosis_note` (Optional[str]): Chẩn đoán y khoa.
  * `approved_at` (Optional[datetime]): Thời điểm bác sĩ duyệt đơn (HITL).
  * `created_at` (datetime): Thời điểm khởi tạo đơn.
  * `items` (List[PrescriptionItemDetailResponse]): Danh sách các chi tiết thuốc thuộc đơn.

---

## PHÂN HỆ 6: LẬP LỊCH AI AGENT (SCHEDULES & AGENTS)

### 6.1 GenerateScheduleRequest / RescheduleRequest
* **Mục đích**: Gửi yêu cầu kích hoạt Planning Agent hoặc Rescheduling Agent rải lại lịch uống thuốc.
* **Module**: `src.modules.agents.schemas`
* **Cấu trúc thuộc tính**:
  * `reason` (Optional[str]): Lý do kích hoạt Agent chạy lại lịch.

### 6.2 AgentRunAsyncResponse
* **Mục đích**: Phản hồi phản hồi nhanh (202 Accepted) chứa mã tiến trình của AI Agent.
* **Module**: `src.modules.agents.schemas`
* **Cấu trúc thuộc tính**:
  * `agent_run_id` (UUID): Mã tiến trình chạy Agent trong bảng `agent_runs`.
  * `status` (str): Trạng thái thực thi (`RUNNING`, `COMPLETED`, `FAILED`).
  * `message` (str): Thông điệp trạng thái.

### 6.3 AgentRunStatusResponse
* **Mục đích**: Phản hồi kết quả và thông số chi tiết của lần chạy AI Agent từ bảng `agent_runs`.
* **Module**: `src.modules.agents.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã lần chạy Agent.
  * `agent_type` (str): Loại Agent (`PLANNING_AGENT`, `RESCHEDULING_AGENT`).
  * `patient_id` (UUID): Mã bệnh nhân.
  * `prescription_id` (Optional[UUID]): Mã đơn thuốc kích hoạt.
  * `trigger_type` (str): Nguồn kích hoạt (`PRESCRIPTION_APPROVED`, `ROUTINE_UPDATED`).
  * `graph_version` (str): Phiên bản đồ thị LangGraph/Workflow.
  * `status` (str): Trạng thái hoàn thành.
  * `latency_ms` (Optional[int]): Thời gian thực thi (mili-giây).
  * `error_code` (Optional[str]): Mã lỗi nếu thất bại.
  * `generated_dose_count` (Optional[int]): Số lượng cữ uống thuốc đã được tự động sinh ra.
  * `created_at` (datetime): Thời điểm chạy.

### 6.4 ChatRequest / ChatResponse / VoiceChatResponse
* **Mục đích**: Trao đổi hội thoại giữa bệnh nhân và AI agent (`POST /chat`, `POST /chat/voice`).
* **Module**: `src.modules.agents.schemas`
* **Ràng buộc định danh**: `ChatRequest` **KHÔNG** có trường `patient_id`. Service luôn lấy `patient_id` từ claim `sub` của access token. Lý do: tool của agent có quyền ghi (`record_dose_action`, `trigger_red_alert`), nên nhận `patient_id` từ body sẽ mở đường ghi dữ liệu sang hồ sơ bệnh nhân khác. Trường thừa gửi kèm trong body bị bỏ qua.
* **Cấu trúc thuộc tính**:
  * `ChatRequest.message` (str, Field min_length=1, max_length=5000): Tin nhắn từ bệnh nhân.
  * `ChatResponse.response` (str): Phản hồi dạng chữ từ agent.
  * `VoiceChatResponse.transcript` (str): Văn bản nhận dạng từ giọng nói.
  * `VoiceChatResponse.response` (str): Phản hồi dạng chữ từ agent.
  * `VoiceChatResponse.audio_base64` (Optional[str]): Phản hồi dạng giọng nói (mp3, base64). `null` khi TTS lỗi (fail-open).

### 6.5 ActiveScheduleResponse
* **Mục đích**: Trả về danh sách các cữ uống thuốc cụ thể trong ngày (`scheduled_doses`) của bệnh nhân.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `patient_id` (UUID): Mã bệnh nhân.
  * `date` (date): Ngày truy vấn lịch.
  * `doses` (List[Dict[str, Any]]): Mảng các cữ uống thuốc đã được rải lịch (Bao gồm `scheduled_dose_id`, `medication_name`, `current_scheduled_at`, `status`, `snooze_count`).

### 6.6 search_drug_info — tool nội bộ, KHÔNG phải HTTP schema
* **Mục đích**: Tra cứu công dụng/hoạt chất thuốc, chỉ gọi được từ bên trong lượt hội thoại `POST /chat`/`/chat/voice` — LLM tự quyết định gọi tool này khi bệnh nhân hỏi về một loại thuốc. Không có route riêng, không nằm trong API contract Slice 8 (đã dời khỏi đó — xem api-contract.md §Slice 8), không nhận request body từ client.
* **Module**: `src.agents.tools.drug_info_tools`
* **Input/Output thật của tool** (không phải Pydantic DTO, chỉ để tham khảo khi debug):
  * `query` (str): tên thuốc hoặc câu hỏi, LLM tự trích từ hội thoại.
  * Trả về (str): **STUB** — hiện luôn trả cố định "Tôi không tìm thấy thông tin đáng tin cậy về thuốc này. Bạn vui lòng hỏi bác sĩ hoặc dược sĩ." bất kể `query` là gì.
* **Chưa tồn tại**: pipeline RAG thật (Chroma collection, embedding, similarity-threshold grounding, citation) — không có `chroma_persist_dir` trong `src/core/config.py`, không có script ingest. `matched_medication_id`/`citations` từng xuất hiện trong bản đặc tả cũ đã bị xoá vì không phản ánh hành vi thật — đừng dựng client mong đợi cấu trúc đó.

---

## PHÂN HỆ 7: DIỂM DANH TUÂN THỦ & AN TOÀN (ADHERENCE & SAFETY)

### 7.1 RecordDoseActionRequest
* **Mục đích**: Tiếp nhận hành động điểm danh cữ uống thuốc của bệnh nhân từ ứng dụng Mobile.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `action` (str): Hành động điểm danh (Enum: `TAKEN`, `SNOOZE`, `SKIPPED`).
  * `action_source` (str, default="PATIENT_MOBILE_APP"): Kênh ghi nhận.
  * `payload` (Dict[str, Any], default={}): Metadata bổ sung (Ví dụ: phút hoãn `snooze_duration_minutes`, ghi chú lý do bỏ qua).

### 7.2 AdherenceLogDetailResponse
* **Mục đích**: Phản hồi bản ghi nhật ký tuân thủ Append-Only vừa được thêm mới vào `adherence_logs`. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[AdherenceLogDetailResponse]`.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã nhật ký.
  * `scheduled_dose_id` (Optional[UUID]): Mã cữ thuốc tương ứng.
  * `patient_id` (UUID): Mã bệnh nhân.
  * `action` (str): Hành động thực hiện.
  * `performed_at` (datetime): Thời điểm ghi nhận hành động.
  * `action_source` (str): Kênh điểm danh.
  * `payload` (Dict[str, Any]): Dữ liệu đính kèm.
  * `idempotency_key` (Optional[str]): Khóa chống ghi nhận lặp.

### 7.3 AdherenceSummaryResponse
* **Mục đích**: Báo cáo tổng hợp tỷ lệ tuân thủ điều trị của bệnh nhân theo khoảng thời gian.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `patient_id` (UUID): Mã bệnh nhân.
  * `from_date` (date): Ngày bắt đầu thống kê.
  * `to_date` (date): Ngày kết thúc thống kê.
  * `adherence_rate` (float): Tỷ lệ tuân thủ điều trị (Phần trăm: `0.0` - `100.0`).
  * `total_doses` (int): Tổng số cữ thuốc trong kỳ.
  * `taken_doses` (int): Số cữ đã uống đúng/đủ.
  * `skipped_doses` (int): Số cữ chủ động bỏ qua.
  * `missed_doses` (int): Số cữ bị quên/quá giờ không uống.

### 7.4 SubmitHealthSurveyRequest
* **Mục đích**: Bệnh nhân gửi khảo sát sức khỏe định kỳ hằng ngày và báo cáo triệu chứng bất thường.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `survey_date` (date): Ngày làm khảo sát.
  * `answers_json` (Dict[str, Any]): Khối JSON chứa các câu trả lời chỉ số (Huyết áp, đường huyết...).
  * `symptoms` (List[Dict[str, Any]], default=[]): Danh sách các triệu chứng ghi nhận (Mỗi triệu chứng gồm `symptom_code`, `severity`: `MILD`/`MODERATE`/`SEVERE`, `description`).

### 7.5 HealthSurveyDetailResponse
* **Mục đích**: Phản hồi kết quả ghi nhận khảo sát từ bảng `health_surveys`.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã bài khảo sát.
  * `patient_id` (UUID): Mã bệnh nhân.
  * `survey_date` (date): Ngày khảo sát.
  * `status` (str): Trạng thái gửi (`SUBMITTED`).
  * `submitted_at` (datetime): Thời điểm nộp khảo sát.

### 7.6 TriggerSosRequest
* **Mục đích**: Tiếp nhận tín hiệu cấp cứu khẩn cấp cho bệnh nhân. Endpoint này phục vụ **hai nguồn**: bệnh nhân bấm nút SOS một chạm, và AI agent phát hiện triệu chứng nặng trong hội thoại (`trigger_red_alert`). Cả hai đều chạy dưới token của chính bệnh nhân nên RBAC không đổi.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `message` (Optional[str]): Thông điệp khẩn cấp hoặc mô tả ngắn sự cố.
  * `metadata` (Dict[str, Any], default={}): Metadata vị trí GPS (`location_lat`, `location_lng`).
  * `triggered_by_type` (Literal["SOS_BUTTON","SEVERE_SYMPTOM","MISSED_DOSES"], default="SOS_BUTTON"): Nguồn kích hoạt, ghi thẳng vào cột `alerts.triggered_by_type`. Không có trường này thì cảnh báo do agent phát hiện bị ghi nhận như bệnh nhân bấm nút, và dashboard bác sĩ không phân biệt được. Giá trị khớp `ck_alerts_triggered_by_type` (migration `0009_slice7_adherence_alerts`).
  * `severity` (Literal["CRITICAL","HIGH","MEDIUM"], default="CRITICAL"): Mức độ nghiêm trọng, ghi vào cột `alerts.severity`. Giá trị khớp `ck_alerts_severity`.
* **Ghi chú tương thích**: hai trường trên đều có default đúng bằng hành vi cũ (`SOS_BUTTON`/`CRITICAL`), nên client đang chạy không cần sửa gì.

### 7.7 ResolveAlertRequest
* **Mục đích**: Bác sĩ gửi phương án xử lý để Đóng cảnh báo (`RESOLVED`).
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `resolution_note` (str, Field min_length=1): Ghi chú kết quả xử lý y khoa.

### 7.8 AlertDetailResponse
* **Mục đích**: Phản hồi chi tiết cảnh báo an toàn Red Alert từ bảng `alerts`. Dùng cho cả API xem chi tiết lẫn item trong phân trang `PageResponse[AlertDetailResponse]`.
* **Module**: `src.modules.adherence.schemas`
* **Cấu trúc thuộc tính**:
  * `id` (UUID): Mã cảnh báo.
  * `patient_id` (UUID): Mã bệnh nhân.
  * `assigned_doctor_id` (Optional[UUID]): Mã bác sĩ tiếp nhận.
  * `triggered_by_type` (str): Nguồn kích hoạt (`SOS_BUTTON`, `SEVERE_SYMPTOM`, `MISSED_DOSES`).
  * `alert_type` (str): Loại cảnh báo (`RED_ALERT`, `WARNING`).
  * `severity` (str): Mức độ nghiêm trọng (`CRITICAL`, `HIGH`, `MEDIUM`).
  * `status` (str): Trạng thái xử lý (`OPEN`, `ACKNOWLEDGED`, `RESOLVED`).
  * `message` (Optional[str]): Nội dung cảnh báo.
  * `created_at` (datetime): Thời điểm phát sinh cảnh báo.

---

## PHÂN HỆ 8: DASHBOARD REALTIME (Doctor Portal)

Slice thuần backend — không có phần nào của agent service tham gia (dashboard chỉ đọc lại dữ liệu adherence/alert như bất kỳ client nào khác). Đã triển khai trong `src/modules/dashboard/`.

Đã xoá khỏi phân hệ này: `CreateOcrJobMultipartRequest`, `OcrJobAsyncResponse`, `OcrJobDetailResponse` (OCR nhãn thuốc + RAG). Không có `ocr_rag` module, không route, không pipeline OCR/Chroma nào tồn tại — giữ lại chỉ tạo ảo giác về một tính năng đang chạy. Đường tra cứu thuốc thật hiện chỉ có `search_drug_info` (xem §6.6), và nó là stub.

> **Đổi module so với bản đặc tả trước.** Ba schema dưới đây từng được ghi là thuộc `src.modules.admin.schemas` / `src.modules.adherence.schemas`. Chúng nằm trong `src.modules.dashboard.schemas` — dashboard là một domain riêng (đọc tổng hợp cho portal bác sĩ), không phải quản trị tài khoản bác sĩ hay ghi nhận tuân thủ; nhét vào 2 module kia là phá nguyên tắc vertical-slice isolation của `structure.md`.

### 8.1 DashboardPatientListResponse
* **Mục đích**: Phản hồi từng item trong danh sách bệnh nhân theo dõi phân trang `PageResponse[DashboardPatientListResponse]` cho Portal Bác sĩ.
* **Module**: `src.modules.dashboard.schemas`
* **Cấu trúc thuộc tính**:
  * `patient_id` (UUID): Mã bệnh nhân.
  * `patient_name` (str): Tên bệnh nhân.
  * `adherence_rate` (float): Tỷ lệ tuân thủ (%) trong cửa sổ trượt `DASHBOARD_ADHERENCE_WINDOW_DAYS` ngày gần nhất (mặc định 7), **không** phải theo khoảng ngày do client chọn.
  * `open_alerts_count` (int): Số cảnh báo còn `OPEN` **hoặc** `ACKNOWLEDGED`. `ACKNOWLEDGED` vẫn tính: bác sĩ đã xem không đồng nghĩa tình trạng bệnh nhân đã xong, ẩn đi sẽ khiến danh sách trông "yên" hơn thực tế.
  * `last_survey_date` (Optional[date]): Ngày khảo sát sức khỏe gần nhất, `null` nếu chưa từng nộp.

### 8.2 DashboardPatientDetailResponse
* **Mục đích**: Phản hồi chi tiết chỉ số tổng hợp của một bệnh nhân trên màn hình Dashboard Bác sĩ.
* **Module**: `src.modules.dashboard.schemas`
* **Cấu trúc thuộc tính**:
  * `patient` (DashboardPatientSummary): `user_id` (UUID), `name` (str), `phone` (str). Là schema có kiểu, không phải `Dict[str, Any]` như bản đặc tả cũ.
  * `active_prescriptions_count` (int): Số đơn thuốc trạng thái `APPROVED`. `DRAFT` chưa có hiệu lực và `CANCELLED` đã hết hiệu lực nên không tính.
  * `adherence_summary` (DashboardAdherenceSummary): `adherence_rate` (float), `total_doses` (int), `taken_doses` (int), `skipped_doses` (int), `missed_doses` (int), `window_days` (int). Có `window_days` để client biết con số này ứng với bao nhiêu ngày, không bị đọc nhầm thành "toàn thời gian".
  * `recent_alerts` (List[AlertDetailResponse]): Cảnh báo gần nhất, mọi trạng thái, tối đa `DASHBOARD_RECENT_ALERTS_LIMIT` (mặc định 5).

### 8.3 WebSocketEventStream
* **Mục đích**: Khối dữ liệu Payload đẩy thời gian thực từ Server xuống Client qua kết nối WebSocket (`/ws/dashboard`).
* **Module**: `src.modules.dashboard.schemas`
* **Cấu trúc thuộc tính**:
  * `event_type` (str): Tên sự kiện. Hiện phát ra: `alert.opened` (SOS hoặc agent phát hiện triệu chứng nặng), `alert.updated` (bác sĩ acknowledge/resolve). `adherence.updated`/`schedule.updated` từng được liệt kê nhưng chưa có publisher nào — đừng dựng client chờ chúng.
  * `timestamp` (datetime): Mốc thời gian phát sinh sự kiện (UTC, ISO 8601).
  * `data` (Dict[str, Any]): Nội dung sự kiện. Với `alert.*` là nguyên `AlertDetailResponse` đã serialize.
* **Đường phát**: envelope do `src.core.redis.publish_dashboard_event` dựng, không phải module dashboard. Lý do: publisher là write path của slice khác (adherence) — bắt chúng import module dashboard chỉ để bắn một event chính là kiểu coupling mà vertical-slice isolation cần tránh. Cùng lý do `src/core/response.py` sở hữu envelope HTTP. Phía dashboard validate lại theo schema này trước khi đẩy xuống socket.