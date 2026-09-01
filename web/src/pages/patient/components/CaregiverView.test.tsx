import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CaregiverLinkDetail } from "../../../types";
import CaregiverView from "./CaregiverView";

const { getCaregiversMock, createCaregiverMock, deleteCaregiverMock } = vi.hoisted(() => ({
  getCaregiversMock: vi.fn(),
  createCaregiverMock: vi.fn(),
  deleteCaregiverMock: vi.fn(),
}));

vi.mock("../../../api", () => ({
  api: {
    getCaregivers: getCaregiversMock,
    createCaregiver: createCaregiverMock,
    deleteCaregiver: deleteCaregiverMock,
  },
  ApiError: class ApiError extends Error {},
}));

const MOCK_CAREGIVERS: CaregiverLinkDetail[] = [
  {
    id: "link-1",
    patient_id: "patient-1",
    phone: "+84901234567",
    relationship: "Con gái",
    link_code: "CG001A",
    telegram_deep_link: "https://t.me/RemindRx_bot?start=CG001A",
    status: "ACTIVE",
    telegram_bound_at: "2026-08-15T08:00:00Z",
    last_message_sent_at: "2026-08-20T08:00:00Z",
    created_at: "2026-08-14T00:00:00Z",
  },
  {
    id: "link-2",
    patient_id: "patient-1",
    phone: "+84909876543",
    relationship: "Em trai",
    link_code: "CG002B",
    telegram_deep_link: "https://t.me/RemindRx_bot?start=CG002B",
    status: "PENDING",
    telegram_bound_at: null,
    last_message_sent_at: null,
    created_at: "2026-08-22T00:00:00Z",
  },
];

describe("CaregiverView", () => {
  beforeEach(() => {
    getCaregiversMock.mockReset().mockResolvedValue(MOCK_CAREGIVERS);
    createCaregiverMock.mockReset();
    deleteCaregiverMock.mockReset();
  });

  it("loads and displays the list of linked caregivers with status badges", async () => {
    render(<CaregiverView patientId="patient-1" onNotice={vi.fn()} />);

    expect(await screen.findByText("Con gái")).toBeInTheDocument();
    expect(screen.getByText("+84901234567")).toBeInTheDocument();
    expect(screen.getByText("Đang hoạt động")).toBeInTheDocument();

    expect(screen.getByText("Em trai")).toBeInTheDocument();
    expect(screen.getByText("+84909876543")).toBeInTheDocument();
    expect(screen.getByText("Chờ người thân bấm Start")).toBeInTheDocument();
  });

  it("submits the create caregiver form and shows Telegram invite box with code", async () => {
    const user = userEvent.setup();
    const onNotice = vi.fn();

    createCaregiverMock.mockResolvedValue({
      id: "link-3",
      patient_id: "patient-1",
      phone: "+84903334455",
      relationship: "Cháu gái",
      link_code: "CG003C",
      telegram_deep_link: "https://t.me/RemindRx_bot?start=CG003C",
      status: "PENDING",
      created_at: "2026-08-25T00:00:00Z",
    });

    render(<CaregiverView patientId="patient-1" onNotice={onNotice} />);
    await screen.findByText("Con gái");

    const phoneInput = screen.getByPlaceholderText("Ví dụ: 0901234567");
    const relationInput = screen.getByPlaceholderText("Ví dụ: Con gái, Vợ, Chồng...");
    const submitBtn = screen.getByRole("button", { name: /thêm người chăm sóc/i });

    await user.type(phoneInput, "0903334455");
    await user.type(relationInput, "Cháu gái");
    await user.click(submitBtn);

    await waitFor(() => {
      expect(createCaregiverMock).toHaveBeenCalledWith("patient-1", {
        caregiver_phone: "0903334455",
        relationship: "Cháu gái",
      });
    });

    expect(await screen.findByText("Mã liên kết Telegram mới được tạo")).toBeInTheDocument();
    expect(screen.getByText("CG003C")).toBeInTheDocument();
    expect(screen.getByText("Mở Telegram")).toBeInTheDocument();
    expect(screen.getByText("Sao chép link mời")).toBeInTheDocument();
    expect(onNotice).toHaveBeenCalledWith("Đã tạo liên kết người chăm sóc thành công.");
  });

  it("handles unlinking a caregiver with confirmation", async () => {
    const user = userEvent.setup();
    const onNotice = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    deleteCaregiverMock.mockResolvedValue({ message: "Caregiver link deleted" });

    render(<CaregiverView patientId="patient-1" onNotice={onNotice} />);
    await screen.findByText("Con gái");

    const deleteButtons = screen.getAllByRole("button", { name: /gỡ liên kết/i });
    await user.click(deleteButtons[0]);

    await waitFor(() => {
      expect(deleteCaregiverMock).toHaveBeenCalledWith("patient-1", "link-1");
    });
    expect(onNotice).toHaveBeenCalledWith("Đã gỡ người chăm sóc.");
  });
});
