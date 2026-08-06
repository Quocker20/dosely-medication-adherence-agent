

-- -----------------------------------------------------------------------------
-- 1. PATIENT PROFILES (Hồ sơ Bệnh nhân & Thông tin liên hệ người thân)
-- -----------------------------------------------------------------------------
CREATE TABLE patient_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(10) CHECK (gender IN ('MALE', 'FEMALE', 'OTHER')),
    fcm_device_token VARCHAR(255),                -- Token nhận Firebase Push Notification
    
    -- Thông tin người thân / Người chăm sóc (Emergency Contact)
    caregiver_name VARCHAR(100),
    caregiver_phone VARCHAR(20),
    caregiver_relationship VARCHAR(50),            -- VD: 'CON_TRAI', 'VO', 'CHONG'
    
    medical_history TEXT,                         -- Tiền sử bệnh
    known_allergies TEXT,                         -- Dị ứng thuốc
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 2. HEALTH LOGS (Nhật ký Sức khỏe & Chỉ số Sinh tồn Bệnh nhân)
-- -----------------------------------------------------------------------------
CREATE TABLE health_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    systolic_bp INT,                               -- Huyết áp tâm thu (mmHg)
    diastolic_bp INT,                              -- Huyết áp tâm trương (mmHg)
    heart_rate INT,                                -- Nhịp tim (bpm)
    blood_glucose DOUBLE PRECISION,                -- Đường huyết (mmol/L hoặc mg/dL)
    glucose_context VARCHAR(30) CHECK (glucose_context IN ('FASTING', 'POST_MEAL', 'RANDOM')),
    sp02 INT,                                      -- Nồng độ O2 trong máu (%)
    body_temperature DOUBLE PRECISION,             -- Thân nhiệt (°C)
    weight_kg DOUBLE PRECISION,                    -- Cân nặng (kg)
    symptoms_note TEXT,                            -- Triệu chứng khai báo chủ quan
    
    recorded_by VARCHAR(20) DEFAULT 'PATIENT' CHECK (recorded_by IN ('PATIENT', 'CAREGIVER', 'DOCTOR')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 3. DOCTOR PROFILES (Hồ sơ Bác sĩ / Cán bộ Y tế)
-- -----------------------------------------------------------------------------
CREATE TABLE doctor_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    specialty VARCHAR(100) DEFAULT 'Nội khoa',
    hospital_department VARCHAR(150),
    security_pin_hash VARCHAR(255) NOT NULL,      -- Mã PIN 6 số xác thực Ký duyệt đơn thuốc
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 4. MEDICINES (Danh mục Dược thư Quốc gia Mẫu)
-- -----------------------------------------------------------------------------
CREATE TABLE medicines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand_name VARCHAR(255) NOT NULL,             -- Tên thương mại & hàm lượng
    active_ingredient TEXT NOT NULL,              -- Hoạt chất chính
    manufacturer VARCHAR(255),                    -- Nhà sản xuất
    therapeutic_uses TEXT,                        -- Công dụng / Nhóm điều trị
    side_effects TEXT,                            -- Tác dụng phụ (Phục vụ AI RAG)
    image_url TEXT,                               -- Ảnh minh họa vỏ thuốc
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 5. PATIENT PREFERENCES (Cài đặt Lịch Sinh hoạt & Cá nhân hóa Bệnh nhân)
-- -----------------------------------------------------------------------------
CREATE TABLE patient_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID UNIQUE NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    
    default_morning_time TIME DEFAULT '07:00:00',
    default_noon_time TIME DEFAULT '11:30:00',
    default_evening_time TIME DEFAULT '18:30:00',
    default_bedtime TIME DEFAULT '21:30:00',
    
    preferred_channel VARCHAR(20) DEFAULT 'PUSH' 
        CHECK (preferred_channel IN ('PUSH', 'ZALO', 'CALLBOT', 'SMS')),
    enable_snooze BOOLEAN DEFAULT TRUE,
    snooze_interval_minutes INT DEFAULT 15,
    max_snooze_count INT DEFAULT 3,
    
    ai_tone VARCHAR(30) DEFAULT 'EMPATHETIC' 
        CHECK (ai_tone IN ('EMPATHETIC', 'FORMAL', 'CONCISE', 'FAMILY_LIKE')),
    app_font_size VARCHAR(15) DEFAULT 'LARGE' 
        CHECK (app_font_size IN ('NORMAL', 'LARGE', 'EXTRA_LARGE')),
        
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 6. PRESCRIPTIONS (Đơn thuốc & Dấu vết Ký duyệt Pháp lý)
-- -----------------------------------------------------------------------------
CREATE TABLE prescriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prescription_code VARCHAR(50) UNIQUE NOT NULL,
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE RESTRICT,
    icd10_code VARCHAR(20),                       -- Mã bệnh lý ICD-10
    diagnosis TEXT NOT NULL,                      -- Chẩn đoán lâm sàng
    status VARCHAR(20) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'APPROVED', 'CANCELLED', 'EXPIRED')),
    
    signed_at TIMESTAMP WITH TIME ZONE,
    signer_ip_address VARCHAR(45),
    signer_user_agent TEXT,
    signature_hash VARCHAR(255),                  -- Hash chữ ký điện tử
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 7. PRESCRIPTION ITEMS (Chi tiết Thuốc & Liều lượng trong đơn)
-- -----------------------------------------------------------------------------
CREATE TABLE prescription_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prescription_id UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
    medicine_id UUID REFERENCES medicines(id) ON DELETE SET NULL,
    
    drug_name VARCHAR(255) NOT NULL,
    active_ingredient VARCHAR(255),
    
    morning_dose DOUBLE PRECISION DEFAULT 0.0,
    noon_dose DOUBLE PRECISION DEFAULT 0.0,
    afternoon_dose DOUBLE PRECISION DEFAULT 0.0,
    night_dose DOUBLE PRECISION DEFAULT 0.0,
    
    timing_relation VARCHAR(30) DEFAULT 'AFTER_MEAL' 
        CHECK (timing_relation IN ('BEFORE_MEAL', 'AFTER_MEAL', 'WITH_MEAL', 'BEDTIME', 'SPECIFIC_TIME')),
    duration_days INT DEFAULT 30,
    special_instructions TEXT,                    -- Hướng dẫn đặc biệt từ Bác sĩ
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 8. REMINDERS (Thời khóa biểu / Lịch mẫu Uống thuốc Cố định)
-- -----------------------------------------------------------------------------
CREATE TABLE reminders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    prescription_item_id UUID NOT NULL REFERENCES prescription_items(id) ON DELETE CASCADE,
    
    scheduled_time TIME NOT NULL,                 -- Giờ uống cố định (VD: '07:00:00')
    dose_amount DOUBLE PRECISION NOT NULL,        -- Số lượng viên/liều uống
    cu_type VARCHAR(20) CHECK (cu_type IN ('MORNING', 'NOON', 'AFTERNOON', 'NIGHT')),
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 9. NOTIFICATIONS (Nhật ký Bắn Thông báo Thực tế - Push / SMS / Email)
-- -----------------------------------------------------------------------------
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    reminder_id UUID REFERENCES reminders(id) ON DELETE CASCADE,
    
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    channel VARCHAR(20) DEFAULT 'PUSH' CHECK (channel IN ('PUSH', 'SMS', 'ZALO', 'EMAIL')),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'CANCELLED')),
    error_message TEXT,                           -- Chi tiết lỗi nếu không bắn được Firebase/SMS
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 10. ADHERENCE LOGS (Nhật ký Tương tác Tuân thủ & Phát hiện Gian dối)
-- -----------------------------------------------------------------------------
CREATE TABLE adherence_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    reminder_id UUID NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    scheduled_date DATE NOT NULL,
    
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'TAKEN', 'SKIPPED', 'DELAYED')),
    confirmed_at TIMESTAMP WITH TIME ZONE,
    user_note TEXT,
    
    escalation_triggered BOOLEAN DEFAULT FALSE,     -- Cờ kích hoạt Cảnh báo đỏ cho Bác sĩ/Người thân
    escalation_reason TEXT,
    
    is_suspicious BOOLEAN DEFAULT FALSE,             -- Cờ gian dối (bấm quá nhanh <5s)
    suspicion_reason VARCHAR(255),                    -- 'CONFIRMED_TOO_FAST', 'BATCH_CONFIRMATION'
    confirmation_latency_seconds INT,                 -- Latency từ lúc nhận Noti -> Bấm nút
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(reminder_id, scheduled_date)
);

-- -----------------------------------------------------------------------------
-- 11. AUDIT LOGS (Nhật ký Dấu vết Vận hành & An toàn Hệ thống)
-- -----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,                                   -- ID Bác sĩ hoặc Bệnh nhân tác động
    user_role VARCHAR(20) CHECK (user_role IN ('DOCTOR', 'PATIENT', 'ADMIN', 'SYSTEM')),
    action VARCHAR(100) NOT NULL,                   -- VD: 'LOGIN', 'SIGN_PRESCRIPTION', 'UPDATE_PREFERENCES'
    entity_name VARCHAR(50),                        -- VD: 'prescriptions', 'patient_profiles'
    entity_id UUID,
    
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 12. CHAT SESSIONS (Phiên Hội thoại AI Chatbot)
-- -----------------------------------------------------------------------------
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,
    session_type VARCHAR(30) DEFAULT 'MEDICATION_CONFIRMATION' 
        CHECK (session_type IN ('MEDICATION_CONFIRMATION', 'GENERAL_QA', 'ESCALATION_FOLLOWUP')),
    related_reminder_id UUID REFERENCES reminders(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 13. MESSAGES (Chi tiết Tin nhắn & Guardrail / RAG Logs)
-- -----------------------------------------------------------------------------
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sender_type VARCHAR(15) NOT NULL CHECK (sender_type IN ('USER', 'AI_BOT', 'SYSTEM', 'DOCTOR')),
    message_text TEXT NOT NULL,
    
    structured_payload JSONB,                      -- Trích xuất NLU (TAKEN / SKIPPED / REASON)
    is_flagged_by_guardrail BOOLEAN DEFAULT FALSE,  -- True nếu vi phạm quy tắc an toàn y tế
    guardrail_trigger_reason TEXT,                  -- 'UNAUTHORIZED_DOSE_CHANGE', 'SELF_MEDICATION'
    rag_sources JSONB,                             -- Nguồn tra cứu từ Dược thư mô phỏng
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
