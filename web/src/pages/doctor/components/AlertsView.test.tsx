import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AlertDetail } from "../../../types";
import AlertsView from "./AlertsView";

const ALERT: AlertDetail = {
  id: "a1",
  patient_id: "p1",
  patient_name: "Nguyễn Văn A",
  assigned_doctor_id: null,
  triggered_by_type: "SOS",
  alert_type: "SOS",
  severity: "HIGH",
  status: "ACKNOWLEDGED",
  message: "m",
  created_at: "2026-10-26T00:00:00Z",
};

describe("AlertsView resolve form", () => {
  it("limits the resolution note to the backend maximum of 1000 characters", () => {
    render(
      <AlertsView
        alerts={[ALERT]}
        patients={[]}
        busyId={null}
        onAcknowledge={vi.fn()}
        onResolve={vi.fn()}
        onOpenPatient={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText(/Ghi chú xử lý/)).toHaveAttribute("maxlength", "1000");
  });
});
