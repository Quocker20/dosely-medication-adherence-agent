import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PatientRoutine } from "../../../types";
import RoutineView from "./RoutineView";

const { patientRoutineMock, updatePatientRoutineMock } = vi.hoisted(() => ({
  patientRoutineMock: vi.fn(),
  updatePatientRoutineMock: vi.fn(),
}));

vi.mock("../../../api", () => ({
  api: {
    patientRoutine: patientRoutineMock,
    updatePatientRoutine: updatePatientRoutineMock,
  },
  ApiError: class ApiError extends Error {},
}));

// WebSocket is not implemented in jsdom; stub it so RoutineView's realtime
// subscription effect doesn't throw. Tests below don't exercise realtime frames.
class StubWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close() {}
}

const BASE_ROUTINE: PatientRoutine = {
  id: "routine-1",
  patient_id: "patient-1",
  wake_time: "06:30:00",
  breakfast_time: "07:00:00",
  lunch_time: "12:00:00",
  dinner_time: "18:30:00",
  sleep_time: "22:00:00",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("RoutineView", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", StubWebSocket as unknown as typeof WebSocket);
    patientRoutineMock.mockReset().mockResolvedValue(BASE_ROUTINE);
    updatePatientRoutineMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function setup() {
    const onScheduleChanged = vi.fn();
    const onNotice = vi.fn();
    render(
      <RoutineView
        patientId="patient-1"
        accessToken="token-abc"
        onScheduleChanged={onScheduleChanged}
        onNotice={onNotice}
      />,
    );
    return { onScheduleChanged, onNotice };
  }

  it("loads the server routine on entry and fills all five time fields", async () => {
    setup();

    expect(await screen.findByDisplayValue("06:30")).toBeInTheDocument();
    expect(screen.getByDisplayValue("07:00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("12:00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("18:30")).toBeInTheDocument();
    expect(screen.getByDisplayValue("22:00")).toBeInTheDocument();
    expect(patientRoutineMock).toHaveBeenCalledWith("patient-1");
  });

  it("keeps Save disabled until a field actually changes", async () => {
    setup();
    await screen.findByDisplayValue("06:30");

    expect(screen.getByRole("button", { name: /Lưu lịch sinh hoạt/ })).toBeDisabled();
  });

  it("sends only the changed field in the PUT payload", async () => {
    updatePatientRoutineMock.mockResolvedValue({ ...BASE_ROUTINE, wake_time: "07:15:00" });
    const user = userEvent.setup();
    setup();

    const wakeInput = await screen.findByDisplayValue("06:30");
    await user.clear(wakeInput);
    await user.type(wakeInput, "07:15");

    const saveButton = screen.getByRole("button", { name: /Lưu lịch sinh hoạt/ });
    await waitFor(() => expect(saveButton).toBeEnabled());
    await user.click(saveButton);

    await waitFor(() => expect(updatePatientRoutineMock).toHaveBeenCalledTimes(1));
    expect(updatePatientRoutineMock).toHaveBeenCalledWith("patient-1", { wake_time: "07:15" });
  });

  it("shows the saved/schedule-updating notice after a successful save", async () => {
    updatePatientRoutineMock.mockResolvedValue({ ...BASE_ROUTINE, wake_time: "07:15:00" });
    const user = userEvent.setup();
    const { onNotice } = setup();

    const wakeInput = await screen.findByDisplayValue("06:30");
    await user.clear(wakeInput);
    await user.type(wakeInput, "07:15");
    await user.click(screen.getByRole("button", { name: /Lưu lịch sinh hoạt/ }));

    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith("Đã lưu lịch sinh hoạt. Lịch nhắc thuốc đang được cập nhật."),
    );
  });

  it("re-fetches the routine when a routine.updated realtime frame arrives", async () => {
    let socket: StubWebSocket | undefined;
    class CapturingWebSocket extends StubWebSocket {
      constructor() {
        super();
        socket = this;
      }
    }
    vi.stubGlobal("WebSocket", CapturingWebSocket as unknown as typeof WebSocket);

    setup();
    await screen.findByDisplayValue("06:30");
    patientRoutineMock.mockClear();

    // Hold the re-fetch pending so the "remote update" banner is observable
    // before load() resolves and clears the flag — the component only shows
    // it for the window between the event and the authoritative re-fetch.
    let resolveReload: ((routine: PatientRoutine) => void) | undefined;
    patientRoutineMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveReload = resolve;
      }),
    );

    act(() => {
      socket?.onmessage?.({ data: JSON.stringify({ event_type: "routine.updated" }) });
    });

    expect(patientRoutineMock).toHaveBeenCalledWith("patient-1");
    expect(await screen.findByText(/Lịch vừa được cập nhật từ thiết bị khác/)).toBeInTheDocument();

    await act(async () => {
      resolveReload?.({ ...BASE_ROUTINE, wake_time: "08:00:00" });
    });

    expect(await screen.findByDisplayValue("08:00")).toBeInTheDocument();
  });
});
