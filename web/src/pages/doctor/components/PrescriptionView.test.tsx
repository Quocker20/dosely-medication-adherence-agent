import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MedicationDetail, PrescriptionDetail } from "../../../types";
import PrescriptionView, { validatePrescriptionItems } from "./PrescriptionView";

const apiMocks = vi.hoisted(() => ({
  medications: vi.fn(),
  patientByPhone: vi.fn(),
  createPrescription: vi.fn(),
  approvePrescription: vi.fn(),
  generateSchedule: vi.fn(),
  schedule: vi.fn(),
}));

const waitForAgentRunMock = vi.hoisted(() => vi.fn());

vi.mock("../../../api", () => ({
  api: apiMocks,
  ApiError: class ApiError extends Error {
    status: number;
    details: string[];
    constructor(message: string, status = 400, details: string[] = []) {
      super(message);
      this.status = status;
      this.details = details;
    }
  },
  waitForAgentRun: waitForAgentRunMock,
}));

const MOCK_MEDICATIONS: MedicationDetail[] = [
  {
    id: "med-1",
    name: "Amlodipine 5mg",
    composition: "Amlodipine besylate 5mg",
    manufacturer: "Pfizer",
    uses: "Hạ huyết áp",
    side_effects: null,
    image_url: null,
    source_name: "Dược thư Quốc gia",
    is_active: true,
  },
  {
    id: "med-2",
    name: "Metformin 500mg",
    composition: "Metformin HCl 500mg",
    manufacturer: "Stada",
    uses: "Hạ đường huyết",
    side_effects: null,
    image_url: null,
    source_name: "Dược thư Quốc gia",
    is_active: true,
  },
];

const MOCK_PRESCRIPTION: PrescriptionDetail = {
  id: "rx-test-1",
  patient_id: "patient-test-1",
  doctor_id: "doc-1",
  status: "APPROVED",
  diagnosis_note: "Tăng huyết áp",
  approved_at: "2026-08-31T00:00:00Z",
  created_at: "2026-08-31T00:00:00Z",
  items: [
    {
      id: "item-1",
      prescription_id: "rx-test-1",
      medication_id: "med-1",
      display_name: "Amlodipine 5mg",
      dose_unit: "Viên",
      morning_dose: "1",
      noon_dose: null,
      evening_dose: null,
      bedtime_dose: null,
      route: "ORAL",
      meal_relation: "AFTER_MEAL",
      minimum_interval_minutes: null,
      start_date: "2026-08-31",
      end_date: null,
      instructions: null,
      is_critical: false,
      created_at: "2026-08-31T00:00:00Z",
    },
  ],
};

describe("validatePrescriptionItems helper", () => {
  it("returns error if items array is empty", () => {
    const errors = validatePrescriptionItems([]);
    expect(errors).toContain("Đơn thuốc phải có ít nhất một loại thuốc.");
  });

  it("returns errors when medication_id, doses, and meal_relation are missing", () => {
    const errors = validatePrescriptionItems([
      {
        medication_id: "",
        dose_unit: "Viên",
        morning_dose: null,
        noon_dose: null,
        evening_dose: null,
        bedtime_dose: null,
        route: "ORAL",
        meal_relation: null,
        minimum_interval_minutes: null,
        start_date: "2026-08-31",
        end_date: null,
        instructions: null,
        is_critical: false,
      },
    ]);

    expect(errors).toHaveLength(3);
    expect(errors[0]).toContain("Vui lòng chọn thuốc trong danh mục");
    expect(errors[1]).toContain("Cần nhập ít nhất một cữ thuốc");
    expect(errors[2]).toContain("Vui lòng chọn thời điểm uống (Trước ăn hoặc Sau ăn)");
  });

  it("returns error if all doses are 0 or negative", () => {
    const errors = validatePrescriptionItems([
      {
        medication_id: "med-1",
        dose_unit: "Viên",
        morning_dose: 0,
        noon_dose: -1,
        evening_dose: 0,
        bedtime_dose: null,
        route: "ORAL",
        meal_relation: "BEFORE_MEAL",
        minimum_interval_minutes: null,
        start_date: "2026-08-31",
        end_date: null,
        instructions: null,
        is_critical: false,
      },
    ]);

    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain("Cần nhập ít nhất một cữ thuốc");
  });

  it("passes validation when bedtime dose is provided and meal_relation is AFTER_MEAL", () => {
    const errors = validatePrescriptionItems([
      {
        medication_id: "med-1",
        dose_unit: "Viên",
        morning_dose: null,
        noon_dose: null,
        evening_dose: null,
        bedtime_dose: 2,
        route: "ORAL",
        meal_relation: "AFTER_MEAL",
        minimum_interval_minutes: null,
        start_date: "2026-08-31",
        end_date: null,
        instructions: null,
        is_critical: false,
      },
    ]);

    expect(errors).toHaveLength(0);
  });
});

describe("PrescriptionView", () => {
  beforeEach(() => {
    apiMocks.medications.mockReset().mockResolvedValue({
      content: MOCK_MEDICATIONS,
      total_elements: 2,
    });
    apiMocks.patientByPhone.mockReset();
    apiMocks.createPrescription.mockReset().mockResolvedValue({
      prescription: MOCK_PRESCRIPTION,
      temp_password: "123",
    });
    apiMocks.approvePrescription.mockReset().mockResolvedValue(MOCK_PRESCRIPTION);
    apiMocks.generateSchedule.mockReset().mockResolvedValue({ agent_run_id: "run-1" });
    waitForAgentRunMock.mockReset().mockResolvedValue({
      status: "COMPLETED",
      generated_dose_count: 1,
    });
    apiMocks.schedule.mockReset().mockResolvedValue({
      patient_id: "patient-test-1",
      date: "2026-08-31",
      doses: [],
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function setup(phoneProp = "0901234567") {
    const onPhone = vi.fn();
    const onToast = vi.fn();
    const onPrescribed = vi.fn();

    render(
      <PrescriptionView
        phone={phoneProp}
        onPhone={onPhone}
        onToast={onToast}
        onPrescribed={onPrescribed}
      />,
    );

    return { onPhone, onToast, onPrescribed };
  }

  async function fillPatientInfo(user: ReturnType<typeof userEvent.setup>) {
    const nameInput = screen.getByLabelText("Họ tên bệnh nhân");
    const dobInput = screen.getByLabelText("Ngày sinh");
    await user.type(nameInput, "Nguyễn Văn Test");
    await user.type(dobInput, "1980-01-01");
  }

  it("renders a new medication row with empty doses and placeholder meal relation", async () => {
    setup();

    const morningInput = screen.getByLabelText("Sáng") as HTMLInputElement;
    const noonInput = screen.getByLabelText("Trưa") as HTMLInputElement;
    const eveningInput = screen.getByLabelText("Chiều") as HTMLInputElement;
    const bedtimeInput = screen.getByLabelText("Trước ngủ") as HTMLInputElement;
    const mealSelect = screen.getByLabelText("Quan hệ bữa ăn") as HTMLSelectElement;

    expect(morningInput.value).toBe("");
    expect(noonInput.value).toBe("");
    expect(eveningInput.value).toBe("");
    expect(bedtimeInput.value).toBe("");
    expect(mealSelect.value).toBe("");

    // Meal relation dropdown options
    const options = Array.from(mealSelect.options).map((opt) => ({
      value: opt.value,
      label: opt.text,
    }));

    expect(options).toEqual([
      { value: "", label: "Chọn thời điểm" },
      { value: "BEFORE_MEAL", label: "Trước ăn" },
      { value: "AFTER_MEAL", label: "Sau ăn" },
    ]);

    expect(screen.queryByText("Trong bữa ăn")).not.toBeInTheDocument();
    expect(screen.queryByText("Không quy định")).not.toBeInTheDocument();
  });

  it("does not call createPrescription from an untouched default medication row", async () => {
    const user = userEvent.setup();
    const { onToast } = setup();

    await fillPatientInfo(user);

    await user.click(screen.getByRole("button", { name: /Duyệt đơn & tạo lịch/i }));

    expect(apiMocks.createPrescription).not.toHaveBeenCalled();
    expect(onToast).toHaveBeenCalledWith("Thông tin đơn thuốc chưa hợp lệ — kiểm tra bên dưới form");
    expect(screen.getByText(/Thuốc 01: Vui lòng chọn thuốc trong danh mục/i)).toBeInTheDocument();
    expect(screen.getByText(/Thuốc 01: Cần nhập ít nhất một cữ thuốc/i)).toBeInTheDocument();
    expect(screen.getByText(/Thuốc 01: Vui lòng chọn thời điểm uống/i)).toBeInTheDocument();
  });

  it("does not call createPrescription when medication is selected but no doses are filled", async () => {
    const user = userEvent.setup();
    const { onToast } = setup();

    await fillPatientInfo(user);

    // Select medication from combobox
    const combobox = screen.getByRole("combobox", { name: "" });
    await user.click(combobox);
    const option = await screen.findByRole("option", { name: /Amlodipine 5mg/i });
    await user.click(option);

    // Select meal relation
    const mealSelect = screen.getByLabelText("Quan hệ bữa ăn");
    await user.selectOptions(mealSelect, "AFTER_MEAL");

    // Click approve without filling any dose
    const approveBtn = screen.getByRole("button", { name: /Duyệt đơn & tạo lịch/i });
    await user.click(approveBtn);

    expect(apiMocks.createPrescription).not.toHaveBeenCalled();
    expect(onToast).toHaveBeenCalledWith("Thông tin đơn thuốc chưa hợp lệ — kiểm tra bên dưới form");
    expect(screen.getByText(/Cần nhập ít nhất một cữ thuốc/i)).toBeInTheDocument();
  });

  it("does not call createPrescription when doses are filled but meal relation is not selected", async () => {
    const user = userEvent.setup();
    const { onToast } = setup();

    await fillPatientInfo(user);

    // Select medication
    const combobox = screen.getByRole("combobox", { name: "" });
    await user.click(combobox);
    const option = await screen.findByRole("option", { name: /Amlodipine 5mg/i });
    await user.click(option);

    // Fill morning dose
    const morningInput = screen.getByLabelText("Sáng");
    await user.type(morningInput, "1");

    // Leave meal relation at default ("")

    // Click approve
    const approveBtn = screen.getByRole("button", { name: /Duyệt đơn & tạo lịch/i });
    await user.click(approveBtn);

    expect(apiMocks.createPrescription).not.toHaveBeenCalled();
    expect(onToast).toHaveBeenCalledWith("Thông tin đơn thuốc chưa hợp lệ — kiểm tra bên dưới form");
    expect(screen.getByText(/Vui lòng chọn thời điểm uống/i)).toBeInTheDocument();
  });

  it("calls createPrescription with correct payload when medication, at least one dose > 0, and meal relation are selected", async () => {
    const user = userEvent.setup();
    const { onPrescribed, onToast } = setup("0901234567");

    await fillPatientInfo(user);

    // Select medication
    const combobox = screen.getByRole("combobox", { name: "" });
    await user.click(combobox);
    const option = await screen.findByRole("option", { name: /Amlodipine 5mg/i });
    await user.click(option);

    // Fill bedtime dose (testing any valid dose > 0)
    const bedtimeInput = screen.getByLabelText("Trước ngủ");
    await user.type(bedtimeInput, "1.5");

    // Select meal relation
    const mealSelect = screen.getByLabelText("Quan hệ bữa ăn");
    await user.selectOptions(mealSelect, "BEFORE_MEAL");

    // Click approve
    const approveBtn = screen.getByRole("button", { name: /Duyệt đơn & tạo lịch/i });
    await user.click(approveBtn);

    await waitFor(() => {
      expect(apiMocks.createPrescription).toHaveBeenCalledTimes(1);
    });

    expect(apiMocks.createPrescription).toHaveBeenCalledWith(
      expect.objectContaining({
        phone: "0901234567",
        name: "Nguyễn Văn Test",
        dob: "1980-01-01",
        sex: "MALE",
        items: [
          expect.objectContaining({
            medication_id: "med-1",
            morning_dose: null,
            noon_dose: null,
            evening_dose: null,
            bedtime_dose: 1.5,
            meal_relation: "BEFORE_MEAL",
          }),
        ],
      }),
    );

    expect(apiMocks.approvePrescription).toHaveBeenCalledWith("rx-test-1");
    expect(onPrescribed).toHaveBeenCalledTimes(1);
    expect(onToast).toHaveBeenCalledWith(expect.stringContaining("Đơn đã duyệt"));
  });

  it("handles adding multiple medication rows and validates each line", async () => {
    const user = userEvent.setup();
    setup();

    await fillPatientInfo(user);

    // Add second medication
    await user.click(screen.getByRole("button", { name: "+ Thêm thuốc" }));

    expect(screen.getByText("Thuốc 01")).toBeInTheDocument();
    expect(screen.getByText("Thuốc 02")).toBeInTheDocument();

    // Fill only first medication
    const comboboxes = screen.getAllByRole("combobox", { name: "" });
    await user.click(comboboxes[0]);
    const option1 = await screen.findByRole("option", { name: /Amlodipine 5mg/i });
    await user.click(option1);

    const morningInputs = screen.getAllByLabelText("Sáng");
    await user.type(morningInputs[0], "1");

    const mealSelects = screen.getAllByLabelText("Quan hệ bữa ăn");
    await user.selectOptions(mealSelects[0], "AFTER_MEAL");

    // Second medication row is still empty, click approve
    const approveBtn = screen.getByRole("button", { name: /Duyệt đơn & tạo lịch/i });
    await user.click(approveBtn);

    expect(apiMocks.createPrescription).not.toHaveBeenCalled();
    // Error details should identify Thuốc 02
    expect(screen.getByText(/Thuốc 02: Vui lòng chọn thuốc trong danh mục/i)).toBeInTheDocument();
    expect(screen.getByText(/Thuốc 02: Cần nhập ít nhất một cữ thuốc/i)).toBeInTheDocument();
    expect(screen.getByText(/Thuốc 02: Vui lòng chọn thời điểm uống/i)).toBeInTheDocument();
  });
});
