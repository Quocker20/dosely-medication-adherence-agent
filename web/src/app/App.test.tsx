import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { navigate } from "../router";
import { setSession } from "../session";
import type { UserResponse } from "../types";
import App from "./App";

const captured = vi.hoisted(() => ({
  doctor: null as null | Record<string, unknown>,
  patient: null as null | Record<string, unknown>,
}));

vi.mock("../pages/doctor/DoctorPortal", () => ({
  default: (props: Record<string, unknown> & {
    onOpenPatient: (id: string) => void;
    onClosePatient: () => void;
  }) => {
    captured.doctor = props;
    return (
      <div data-testid="doctor-portal">
        <button onClick={() => props.onOpenPatient("patient-77")}>open-patient</button>
        <button onClick={() => props.onClosePatient()}>close-patient</button>
      </div>
    );
  },
}));

vi.mock("../pages/patient/PatientPortal", () => ({
  default: (props: Record<string, unknown>) => {
    captured.patient = props;
    return <div data-testid="patient-portal" />;
  },
}));

vi.mock("../pages/admin/AdminPortal", () => ({
  default: () => <div data-testid="admin-portal" />,
}));

const DOCTOR_USER: UserResponse = { id: "doc-1", phone: "0911111111", role: "DOCTOR", status: "ACTIVE" };
const PATIENT_USER: UserResponse = { id: "pat-1", phone: "0922222222", role: "PATIENT", status: "ACTIVE" };

function loginAs(user: UserResponse) {
  setSession({ accessToken: "access-token", refreshToken: "refresh-token", user });
}

describe("App routing", () => {
  beforeEach(() => {
    window.localStorage.clear();
    captured.doctor = null;
    captured.patient = null;
  });

  afterEach(() => {
    setSession(null);
  });

  it("renders the patient detail page with the id from the URL (direct link)", async () => {
    loginAs(DOCTOR_USER);
    navigate("/doctor/patients/patient-42");

    render(<App />);

    expect(await screen.findByTestId("doctor-portal")).toBeInTheDocument();
    expect(captured.doctor).toMatchObject({ view: "patients", patientDetailId: "patient-42" });
  });

  it("has patientDetailId null on the plain patients list route", async () => {
    loginAs(DOCTOR_USER);
    navigate("/doctor/patients");

    render(<App />);

    await screen.findByTestId("doctor-portal");
    expect(captured.doctor).toMatchObject({ view: "patients", patientDetailId: null });
  });

  it("opening a patient navigates to /doctor/patients/:id", async () => {
    loginAs(DOCTOR_USER);
    navigate("/doctor/patients");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByTestId("doctor-portal");

    await user.click(screen.getByText("open-patient"));

    expect(window.location.pathname).toBe("/doctor/patients/patient-77");
    expect(captured.doctor).toMatchObject({ patientDetailId: "patient-77" });
  });

  it("closing a patient (Back) returns to the patients list and supports browser Back", async () => {
    loginAs(DOCTOR_USER);
    navigate("/doctor/patients/patient-42");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByTestId("doctor-portal");

    await user.click(screen.getByText("close-patient"));
    expect(window.location.pathname).toBe("/doctor/patients");
    expect(captured.doctor).toMatchObject({ patientDetailId: null });

    // Simulate the browser's own Back button (a popstate the router didn't cause).
    window.history.pushState({}, "", "/doctor/patients/patient-42");
    window.dispatchEvent(new PopStateEvent("popstate"));

    await screen.findByTestId("doctor-portal");
    expect(captured.doctor).toMatchObject({ patientDetailId: "patient-42" });
  });

  it("routes a patient session to the Lịch sinh hoạt (routine) tab", async () => {
    loginAs(PATIENT_USER);
    navigate("/patient/routine");

    render(<App />);

    await screen.findByTestId("patient-portal");
    expect(captured.patient).toMatchObject({ tab: "routine" });
  });

  it("falls back to the default tab for an unknown doctor route segment", async () => {
    loginAs(DOCTOR_USER);
    navigate("/doctor/not-a-real-tab");

    render(<App />);

    await screen.findByTestId("doctor-portal");
    expect(captured.doctor).toMatchObject({ view: "dashboard", patientDetailId: null });
  });
});
