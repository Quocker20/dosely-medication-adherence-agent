import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../api";
import ChatView from "./ChatView";

vi.mock("../../../api", () => ({
  api: {
    chatConversations: vi.fn(),
    chatConversationDetail: vi.fn(),
    patientChat: vi.fn(),
    patientChatVoice: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

const mockConversations = [
  {
    id: "conv-1",
    title: "Hỏi về huyết áp",
    preview: "Huyết áp của tôi hôm nay 140/90",
    messageCount: 2,
    createdAt: "2026-08-30T10:00:00.000Z",
    updatedAt: "2026-08-30T10:05:00.000Z",
  },
  {
    id: "conv-2",
    title: "Hỏi về thuốc Metformin",
    preview: "Uống thuốc sau khi ăn",
    messageCount: 4,
    createdAt: "2026-08-29T08:00:00.000Z",
    updatedAt: "2026-08-29T08:10:00.000Z",
  },
];

describe("ChatView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.chatConversations).mockResolvedValue({
      content: mockConversations,
      page_no: 1,
      page_size: 30,
      total_elements: 2,
      total_pages: 1,
      last: true,
    });
  });

  it("renders welcome message and loads conversations list", async () => {
    render(<ChatView patientId="p-01" />);

    expect(screen.getByText(/Chào bạn! Tôi là trợ lý RemindRx/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(api.chatConversations).toHaveBeenCalledWith(1, 30);
      expect(screen.getByText("Hỏi về huyết áp")).toBeInTheDocument();
      expect(screen.getByText("Hỏi về thuốc Metformin")).toBeInTheDocument();
    });
  });

  it("shows title-only history, one new-chat control, and no suggested chips", async () => {
    render(<ChatView patientId="p-01" />);

    await waitFor(() => {
      expect(screen.getByText("Hỏi về huyết áp")).toBeInTheDocument();
    });

    expect(screen.queryByText("Huyết áp của tôi hôm nay 140/90")).not.toBeInTheDocument();
    expect(screen.queryByText("Liều tiếp theo lúc mấy giờ?")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Cuộc trò chuyện mới/i })).toHaveLength(1);
  });

  it("loads conversation detail when a conversation is clicked", async () => {
    vi.mocked(api.chatConversationDetail).mockResolvedValue({
      id: "conv-1",
      title: "Hỏi về huyết áp",
      createdAt: "2026-08-30T10:00:00.000Z",
      updatedAt: "2026-08-30T10:05:00.000Z",
      messages: [
        {
          id: "m-1",
          role: "user",
          content: "Huyết áp hôm nay cao quá",
          createdAt: "2026-08-30T10:00:00.000Z",
        },
        {
          id: "m-2",
          role: "assistant",
          content: "Bạn hãy ngồi nghỉ ngơi và đo lại sau 15 phút nhé.",
          createdAt: "2026-08-30T10:01:00.000Z",
        },
      ],
      hasMore: false,
      nextCursor: null,
    });

    render(<ChatView patientId="p-01" />);

    await waitFor(() => {
      expect(screen.getByText("Hỏi về huyết áp")).toBeInTheDocument();
    });

    const convItem = screen.getByText("Hỏi về huyết áp");
    await act(async () => {
      fireEvent.click(convItem);
    });

    expect(api.chatConversationDetail).toHaveBeenCalledWith("conv-1");
    await waitFor(() => {
      expect(screen.getByText("Huyết áp hôm nay cao quá")).toBeInTheDocument();
      expect(screen.getByText("Bạn hãy ngồi nghỉ ngơi và đo lại sau 15 phút nhé.")).toBeInTheDocument();
    });
  });

  it("resets to welcome message on start new chat click", async () => {
    render(<ChatView patientId="p-01" />);

    const newChatBtn = screen.getByRole("button", { name: /Cuộc trò chuyện mới/i });
    act(() => {
      fireEvent.click(newChatBtn);
    });

    expect(screen.getByText(/Chào bạn! Tôi là trợ lý RemindRx/i)).toBeInTheDocument();
  });

  it("sends a message and reloads conversation list", async () => {
    vi.mocked(api.patientChat).mockResolvedValue({
      response: "Thuốc nên uống sau bữa ăn sáng.",
      conversationId: "new-conv-id",
    });

    render(<ChatView patientId="p-01" />);

    const textarea = screen.getByPlaceholderText(/Hỏi về thuốc hoặc lịch uống…/i);
    fireEvent.change(textarea, { target: { value: "Uống thuốc lúc nào?" } });

    const sendBtn = screen.getByRole("button", { name: /Gửi tin nhắn/i });
    await act(async () => {
      fireEvent.click(sendBtn);
    });

    expect(api.patientChat).toHaveBeenCalledWith("Uống thuốc lúc nào?", expect.any(String));
    await waitFor(() => {
      expect(screen.getByText("Thuốc nên uống sau bữa ăn sáng.")).toBeInTheDocument();
    });
  });

  it("uses a fresh conversation id after starting a new chat", async () => {
    vi.mocked(api.patientChat)
      .mockResolvedValueOnce({
        response: "Trả lời đoạn chat cũ.",
        conversationId: "server-conv-1",
      })
      .mockResolvedValueOnce({
        response: "Trả lời đoạn chat mới.",
        conversationId: "server-conv-2",
      });

    render(<ChatView patientId="p-01" />);

    const textarea = screen.getByPlaceholderText(/Hỏi về thuốc hoặc lịch uống…/i);
    fireEvent.change(textarea, { target: { value: "Câu đầu" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Gửi tin nhắn/i }));
    });

    await waitFor(() => {
      expect(api.patientChat).toHaveBeenCalledTimes(1);
    });

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /Cuộc trò chuyện mới/i }));
    });
    fireEvent.change(textarea, { target: { value: "Câu mới" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Gửi tin nhắn/i }));
    });

    await waitFor(() => {
      expect(api.patientChat).toHaveBeenCalledTimes(2);
    });
    const firstConversationId = vi.mocked(api.patientChat).mock.calls[0][1];
    const secondConversationId = vi.mocked(api.patientChat).mock.calls[1][1];
    expect(secondConversationId).not.toBe(firstConversationId);
    expect(secondConversationId).not.toBe("server-conv-1");
  });

  it("does not load a history item while a message is sending", async () => {
    vi.mocked(api.patientChat).mockImplementation(() => new Promise(() => {}));

    render(<ChatView patientId="p-01" />);

    await waitFor(() => {
      expect(screen.getByText("Hỏi về huyết áp")).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/Hỏi về thuốc hoặc lịch uống…/i);
    fireEvent.change(textarea, { target: { value: "Đang gửi" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Gửi tin nhắn/i }));
    });

    await waitFor(() => {
      expect(api.patientChat).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByText("Hỏi về huyết áp"));

    expect(api.chatConversationDetail).not.toHaveBeenCalled();
  });

  it("toggles sidebar visibility", () => {
    render(<ChatView patientId="p-01" />);

    const toggleBtn = screen.getByRole("button", { name: /Lịch sử trò chuyện/i });
    expect(screen.getByText("Lịch sử chat")).toBeInTheDocument();

    act(() => {
      fireEvent.click(toggleBtn);
    });
    expect(screen.queryByText("Lịch sử chat")).not.toBeInTheDocument();

    act(() => {
      fireEvent.click(toggleBtn);
    });
    expect(screen.getByText("Lịch sử chat")).toBeInTheDocument();
  });

  it("grows the composer to its maximum height and then enables scrolling", async () => {
    render(<ChatView patientId="p-01" />);

    const textarea = screen.getByPlaceholderText(/Hỏi về thuốc hoặc lịch uống…/i);
    Object.defineProperty(textarea, "scrollHeight", { configurable: true, value: 160 });
    fireEvent.change(textarea, { target: { value: "Nội dung xuống dòng\n".repeat(12) } });

    await waitFor(() => {
      expect(textarea).toHaveStyle({ height: "110px", overflowY: "auto" });
    });
  });
});
