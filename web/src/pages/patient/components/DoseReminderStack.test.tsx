import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DoseReminderStack from "./DoseReminderStack";
import type { DoseReminder } from "./useFcmReminders";

const sampleReminders: DoseReminder[] = [
  {
    id: "rem-1",
    title: "Đến giờ uống thuốc",
    body: "Metformin 500mg (1 viên), Amlodipine 5mg (1 viên)",
    firedAt: "2026-08-30T08:00:00.000Z",
    read: false,
  },
  {
    id: "rem-2",
    title: "Đến giờ uống thuốc trưa",
    body: "Paracetamol 500mg (1 viên)",
    firedAt: "2026-08-30T12:00:00.000Z",
    read: false,
  },
];

describe("DoseReminderStack", () => {
  it("renders nothing when reminders array is empty", () => {
    const { container } = render(<DoseReminderStack reminders={[]} onDismiss={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders all reminders in stack with title and body", () => {
    render(<DoseReminderStack reminders={sampleReminders} onDismiss={vi.fn()} />);

    expect(screen.getByText("Đến giờ uống thuốc")).toBeInTheDocument();
    expect(screen.getByText("Metformin 500mg (1 viên), Amlodipine 5mg (1 viên)")).toBeInTheDocument();
    expect(screen.getByText("Đến giờ uống thuốc trưa")).toBeInTheDocument();
    expect(screen.getByText("Paracetamol 500mg (1 viên)")).toBeInTheDocument();
  });

  it("calls onDismiss when close button is clicked", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();

    render(<DoseReminderStack reminders={[sampleReminders[0]]} onDismiss={onDismiss} />);

    const closeButton = screen.getByRole("button", { name: /Đóng thông báo/i });
    act(() => {
      fireEvent.click(closeButton);
    });

    // Advance leaving animation time (220ms)
    act(() => {
      vi.advanceTimersByTime(250);
    });

    expect(onDismiss).toHaveBeenCalledWith("rem-1");
    vi.useRealTimers();
  });

  it("auto-dismisses card after 12s timeout", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();

    render(<DoseReminderStack reminders={[sampleReminders[0]]} onDismiss={onDismiss} />);

    expect(onDismiss).not.toHaveBeenCalled();

    // Advance 12 seconds
    act(() => {
      vi.advanceTimersByTime(12000);
    });

    expect(onDismiss).toHaveBeenCalledWith("rem-1");
    vi.useRealTimers();
  });

  it("clears the auto-dismiss timer on unmount", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();

    const { unmount } = render(<DoseReminderStack reminders={[sampleReminders[0]]} onDismiss={onDismiss} />);
    unmount();

    act(() => {
      vi.advanceTimersByTime(12000);
    });

    expect(onDismiss).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
