import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActiveSchedule,
  AdherenceLog,
  AlertDetail,
  DashboardPatientDetail,
  HealthSurveyFullDetail,
  PatientDetail,
  PatientRoutine,
  PrescriptionDetail,
} from "../../../types";
import PatientDetailPage from "./PatientDetailPage";

const apiMocks = vi.hoisted(() => ({
  patient: vi.fn(),
  dashboardPatientDetail: vi.fn(),
  patientPrescriptions: vi.fn(),
  adherenceLogs: vi.fn(),
  alerts: vi.fn(),
  patientHealthSurveys: vi.fn(),
  healthSurveyDetail: vi.fn(),
  patientRoutine: vi.fn(),
  schedule: vi.fn(),
  generateSchedule: vi.fn(),
}));

vi.mock("../../../api", () => ({
  api: apiMocks,
  ApiError: class ApiError extends Error {},
  waitForAgentRun: vi.fn(),
}));

class StubWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close() {}
}

const PROFILE: PatientDetail = {
  user_id: "patient-1",
  phone: "0900000000",
  role: "PATIENT",
  status: "ACTIVE",
  name: "Nguyễn Văn A",
  dob: "1970-01-01",
  sex: "MALE",
  timezone: "Asia/Ho_Chi_Minh",
  privacy_consent_status: "GRANTED",
  emergency_note: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const DETAIL: DashboardPatientDetail = {
  patient: { user_id: "patient-1", name: "Nguyễn Văn A", phone: "0900000000" },
  active_prescriptions_count: 1,
  adherence_summary: {
    adherence_rate: 82,
    total_doses: 40,
    taken_doses: 33,
    skipped_doses: 4,
    missed_doses: 3,
    window_days: 30,
  },
  recent_alerts: [],
};

const PRESCRIPTIONS: PrescriptionDetail[] = [
  {
    id: "rx-1",
    patient_id: "patient-1",
    doctor_id: "doc-1",
    status: "APPROVED",
    diagnosis_note: "Tăng huyết áp",
    approved_at: "2026-01-05T00:00:00Z",
    created_at: "2026-01-04T00:00:00Z",
    items: [
      {
        id: "item-1",
        prescription_id: "rx-1",
        medication_id: "med-1",
        display_name: "Amlodipine 5mg",
        dose_unit: "viên",
        morning_dose: "1",
        noon_dose: null,
        evening_dose: null,
        bedtime_dose: null,
        route: "Uống",
        meal_relation: "Sau ăn",
        minimum_interval_minutes: null,
        start_date: "2026-01-05",
        end_date: null,
        instructions: "Uống với nhiều nước",
        created_at: "2026-01-04T00:00:00Z",
      },
    ],
  },
];

const LOGS: AdherenceLog[] = [];
const ALERTS: AlertDetail[] = [];
const SURVEYS: HealthSurveyFullDetail[] = [];
const ROUTINE: PatientRoutine = {
  id: "routine-1",
  patient_id: "patient-1",
  wake_time: "06:30:00",
  breakfast_time: "07:00:00",
  lunch_time: "12:00:00",
  dinner_time: "18:30:00",
  sleep_time: "22:00:00",
  updated_at: "2026-01-01T00:00:00Z",
};
const SCHEDULE: ActiveSchedule = { patient_id: "patient-1", date: "2026-08-28", doses: [] };

describe("PatientDetailPage", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", StubWebSocket as unknown as typeof WebSocket);
    apiMocks.patient.mockReset().mockResolvedValue(PROFILE);
    apiMocks.dashboardPatientDetail.mockReset().mockResolvedValue(DETAIL);
    apiMocks.patientPrescriptions.mockReset().mockResolvedValue({ content: PRESCRIPTIONS, total_elements: 1 });
    apiMocks.adherenceLogs.mockReset().mockResolvedValue({ content: LOGS, total_elements: 0 });
    apiMocks.alerts.mockReset().mockResolvedValue({ content: ALERTS, total_elements: 0 });
    apiMocks.patientHealthSurveys.mockReset().mockResolvedValue({ content: [], total_elements: 0 });
    apiMocks.healthSurveyDetail.mockReset().mockResolvedValue(SURVEYS[0]);
    apiMocks.patientRoutine.mockReset().mockResolvedValue(ROUTINE);
    apiMocks.schedule.mockReset().mockResolvedValue(SCHEDULE);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function setup() {
    const onBack = vi.fn();
    const onPrescribe = vi.fn();
    const onToast = vi.fn();
    render(
      <PatientDetailPage
        patientId="patient-1"
        accessToken="token-abc"
        onBack={onBack}
        onPrescribe={onPrescribe}
        onToast={onToast}
      />,
    );
    return { onBack, onPrescribe, onToast };
  }

  it("shows a loading state, then the Overview tab with identity and adherence KPIs", async () => {
    setup();
    expect(screen.getByText(/Đang tải hồ sơ bệnh nhân/)).toBeInTheDocument();

    expect(await screen.findByRole("heading", { name: "Nguyễn Văn A" })).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText(/33\/40 cữ đã uống/)).toBeInTheDocument();
  });

  it("shows an error state with a way back when a fetch fails", async () => {
    apiMocks.dashboardPatientDetail.mockReset().mockRejectedValue(new Error("boom"));
    const { onBack } = setup();

    expect(await screen.findByText("Không mở được hồ sơ bệnh nhân")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Quay lại danh sách" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("calls onBack when the back control is used", async () => {
    const { onBack } = setup();
    await screen.findByRole("heading", { name: "Nguyễn Văn A" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Danh sách bệnh nhân/ }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("shows read-only medication instructions with no dose/frequency/route edit controls", async () => {
    const user = userEvent.setup();
    setup();
    await screen.findByRole("heading", { name: "Nguyễn Văn A" });

    await user.click(screen.getByRole("tab", { name: "Thuốc đang điều trị" }));

    const medicationsPanel = await screen.findByText("Amlodipine 5mg");
    expect(medicationsPanel).toBeInTheDocument();
    expect(screen.getByText(/Thông tin chỉ đọc/)).toBeInTheDocument();
    expect(screen.getByText(/Sáng 1 viên/)).toBeInTheDocument();
    // No editable dose/frequency/route/duration inputs anywhere on the tab —
    // HITL requires those only ever change through a new prescription.
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
  });

  it("shows the routine tab as read-only text, not editable inputs", async () => {
    const user = userEvent.setup();
    setup();
    await screen.findByRole("heading", { name: "Nguyễn Văn A" });

    await user.click(screen.getByRole("tab", { name: "Lịch sinh hoạt & nhắc thuốc" }));

    const wakeTime = await screen.findByText("06:30");
    expect(wakeTime.tagName).toBe("TIME");
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    // Safe actions remain available even from the read-only routine tab.
    expect(screen.getByRole("button", { name: "Kê đơn mới" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tính lại lịch nhắc" })).toBeInTheDocument();
  });

  it("switches to the Health & adherence tab and shows adherence/survey data", async () => {
    apiMocks.adherenceLogs.mockReset().mockResolvedValue({
      content: [{ id: "log-1", scheduled_dose_id: "d1", patient_id: "patient-1", action: "TAKEN", performed_at: "2026-08-27T08:00:00Z", action_source: "PATIENT", payload: {}, idempotency_key: null }],
      total_elements: 1,
    });
    const user = userEvent.setup();
    setup();
    await screen.findByRole("heading", { name: "Nguyễn Văn A" });

    await user.click(screen.getByRole("tab", { name: "Sức khỏe & tuân thủ" }));

    const healthPanel = within(screen.getByText("Nhật ký tuân thủ").closest("article") as HTMLElement);
    expect(healthPanel.getByText("TAKEN")).toBeInTheDocument();
  });

  it("re-fetches patient data only when a matching dashboard realtime frame arrives", async () => {
    let socket: StubWebSocket | undefined;
    class CapturingWebSocket extends StubWebSocket {
      constructor() {
        super();
        socket = this;
      }
    }
    vi.stubGlobal("WebSocket", CapturingWebSocket as unknown as typeof WebSocket);

    setup();
    await screen.findByRole("heading", { name: "Nguyễn Văn A" });
    apiMocks.dashboardPatientDetail.mockClear();

    socket?.onmessage?.({
      data: JSON.stringify({ event_type: "routine.updated", data: { patient_id: "some-other-patient" } }),
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.dashboardPatientDetail).not.toHaveBeenCalled();

    socket?.onmessage?.({
      data: JSON.stringify({ event_type: "routine.updated", data: { patient_id: "patient-1" } }),
    });
    await waitFor(() => expect(apiMocks.dashboardPatientDetail).toHaveBeenCalledTimes(1));
  });
});
