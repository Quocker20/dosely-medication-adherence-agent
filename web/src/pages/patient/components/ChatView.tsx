import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../../../api";
import type { ChatConversationListItem } from "../../../types";
import Icon from "./Icon";


interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
}

const COMPOSER_MIN_HEIGHT = 42;
const COMPOSER_MAX_HEIGHT = 110;
/** Lịch sử chat lưu theo phiên trình duyệt, tách theo bệnh nhân để không lẫn. */
export function chatStorageKey(patientId: string) {
  return `remindrx.patient-chat.${patientId}`;
}
function welcomeChatMessages(): ChatMessage[] {
  return [
    {
      id: "welcome",
      role: "assistant",
      content:
        "Chào bạn! Tôi là trợ lý RemindRx. Tôi có thể giúp bạn tra cứu lịch uống thuốc, giải thích thông tin thuốc từ nguồn tham khảo và ghi nhận vấn đề cần bác sĩ xem xét.",
      time: "Bây giờ",
    },
  ];
}

function formatMessageTime(dateString?: string): string {
  if (!dateString) return "Bây giờ";
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return "Bây giờ";
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "Bây giờ";
  }
}

function formatConversationDate(dateString?: string): string {
  if (!dateString) return "";
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return "";
    const today = new Date();
    if (d.toDateString() === today.toDateString()) {
      return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  } catch {
    return "";
  }
}

export default function ChatView({ patientId: _patientId }: { patientId?: string }) {
  const [conversations, setConversations] = useState<ChatConversationListItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>(welcomeChatMessages);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const conversationIdRef = useRef<string>(crypto.randomUUID());
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<number | null>(null);
  const discardRecordingRef = useRef(false);

  const voiceSupported = useMemo(
    () => typeof window !== "undefined" && "MediaRecorder" in window && Boolean(navigator.mediaDevices?.getUserMedia),
    [],
  );
  const loadConversations = useCallback(async () => {
    try {
      setLoadingHistory(true);
      const res = await api.chatConversations(1, 30);
      setConversations(res.content);
    } catch {
      // Fail-open: chat still works even if list fails
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, busy]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, COMPOSER_MIN_HEIGHT), COMPOSER_MAX_HEIGHT);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > COMPOSER_MAX_HEIGHT ? "auto" : "hidden";
  }, [input]);

  const selectConversation = async (conv: ChatConversationListItem) => {
    if (conv.id === activeConversationId || busy || recording) return;
    try {
      setBusy(true);
      setError(null);
      setActiveConversationId(conv.id);
      conversationIdRef.current = conv.id;
      const detail = await api.chatConversationDetail(conv.id);
      const mapped: ChatMessage[] = detail.messages.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        time: formatMessageTime(m.createdAt),
      }));
      setMessages(mapped.length > 0 ? mapped : welcomeChatMessages());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không thể tải nội dung cuộc trò chuyện.");
    } finally {
      setBusy(false);
    }
  };

  const startNewChat = () => {
    if (busy || recording) return;
    setActiveConversationId(null);
    conversationIdRef.current = crypto.randomUUID();
    setMessages(welcomeChatMessages());
    setError(null);
  };

  const stopRecording = useCallback(() => {
    if (recordingTimeoutRef.current !== null) {
      window.clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  useEffect(() => () => {
    discardRecordingRef.current = true;
    stopRecording();
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }, [stopRecording]);

  async function send(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || busy || recording) return;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError(null);
    setBusy(true);
    const wasNewChat = activeConversationId === null;
    try {
      const result = await api.patientChat(message, conversationIdRef.current);
      if (result.conversationId) {
        conversationIdRef.current = result.conversationId;
        if (wasNewChat) {
          setActiveConversationId(result.conversationId);
        }
      }
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: result.response,
          time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      void loadConversations();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    if (!voiceSupported || busy || recording) return;
    setError(null);
    discardRecordingRef.current = false;
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const currentStream = recorder.stream;
        if (recordingTimeoutRef.current !== null) {
          window.clearTimeout(recordingTimeoutRef.current);
          recordingTimeoutRef.current = null;
        }
        recorderRef.current = null;
        currentStream.getTracks().forEach((track) => track.stop());
        if (discardRecordingRef.current) return;
        setRecording(false);
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (audio.size === 0) {
          setError("Không nhận được âm thanh. Vui lòng thử lại.");
          return;
        }
        setBusy(true);
        const wasNewChat = activeConversationId === null;
        try {
          const result = await api.patientChatVoice(audio, conversationIdRef.current);
          if (result.conversationId) {
            conversationIdRef.current = result.conversationId;
            if (wasNewChat) {
              setActiveConversationId(result.conversationId);
            }
          }
          const time = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
          setMessages((current) => [
            ...current,
            { id: crypto.randomUUID(), role: "user", content: result.transcript, time },
            { id: crypto.randomUUID(), role: "assistant", content: result.response, time },
          ]);
          void loadConversations();
        } catch (cause) {
          setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại.");
        } finally {
          setBusy(false);
        }
      };
      recorder.start();
      setRecording(true);
      recordingTimeoutRef.current = window.setTimeout(stopRecording, 60_000);
    } catch (cause) {
      stream?.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      setRecording(false);
      setError(
        cause instanceof DOMException && cause.name === "NotAllowedError"
          ? "Bạn cần cho phép dùng micro để gửi tin nhắn thoại."
          : "Không thể bắt đầu ghi âm. Vui lòng thử lại.",
      );
    }
  }

  return (
    <section className="chat-layout">
      {showSidebar && (
        <aside className="web-card chat-sidebar" aria-label="Lịch sử hội thoại">
          <div className="chat-sidebar-head">
            <div className="chat-sidebar-title">
              <Icon name="history" size={18} />
              <span>Lịch sử chat</span>
            </div>
            <button
              type="button"
              className="chat-new-btn"
              onClick={startNewChat}
              title="Tạo cuộc trò chuyện mới"
              aria-label="Cuộc trò chuyện mới"
            >
              + Mới
            </button>
          </div>
          <div className="chat-history-list">
            {loadingHistory && conversations.length === 0 ? (
              <div className="chat-history-empty">Đang tải lịch sử…</div>
            ) : conversations.length === 0 ? (
              <div className="chat-history-empty">Chưa có cuộc trò chuyện nào</div>
            ) : (
              conversations.map((conv) => {
                const isActive = conv.id === activeConversationId;
                return (
                  <button
                    key={conv.id}
                    type="button"
                    className={`chat-history-item ${isActive ? "active" : ""}`}
                    onClick={() => void selectConversation(conv)}
                  >
                    <div className="chat-item-header">
                      <strong className="chat-item-title">{conv.title}</strong>
                      <time className="chat-item-time">{formatConversationDate(conv.updatedAt)}</time>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>
      )}

      <div className="web-card chat-panel">
        <header className="chat-panel-head">
          <div className="chat-head-left">
            <button
              type="button"
              className="chat-toggle-sidebar-btn"
              onClick={() => setShowSidebar((s) => !s)}
              title={showSidebar ? "Ẩn lịch sử" : "Hiện lịch sử"}
              aria-label="Lịch sử trò chuyện"
            >
              <Icon name="menu" size={18} />
            </button>
            <div className="chat-avatar">
              <Icon name="assistant" size={22} />
            </div>
          </div>
          <div>
            <h2>Trợ lý AI</h2>
            <p>Thuốc & lịch uống · RemindRx</p>
          </div>
        </header>

        <div className="chat-warning">
          <Icon name="alert" size={17} />
          <span>AI chỉ cung cấp thông tin tham khảo; không tự thay đổi liều, kê đơn hoặc xử trí cấp cứu qua chat.</span>
        </div>

        <div className="chat-messages">
          {messages.map((message) => (
            <div key={message.id} className={`chat-row ${message.role}`}>
              <div className="chat-bubble">
                {message.role === "assistant" && <b>RemindRx AI</b>}
                <p>{message.content}</p>
                <time>{message.time}</time>
              </div>
            </div>
          ))}
          {busy && (
            <div className="chat-row assistant">
              <div className="chat-bubble chat-typing">
                <i />
                <i />
                <i />
                <span>Đang tra cứu…</span>
              </div>
            </div>
          )}
          {error && <div className="chat-error">{error}</div>}
          <div ref={bottomRef} />
        </div>

        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            disabled={recording}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(input);
              }
            }}
            maxLength={5000}
            rows={1}
            placeholder="Hỏi về thuốc hoặc lịch uống…"
          />
          {voiceSupported && (
            <button
              className={`chat-mic ${recording ? "recording" : ""}`}
              type="button"
              disabled={busy}
              onClick={() => {
                if (recording) stopRecording();
                else void startRecording();
              }}
              aria-label={recording ? "Dừng ghi âm" : "Gửi tin nhắn thoại"}
            >
              <Icon name="mic" size={19} />
            </button>
          )}
          <button
            className="chat-send"
            type="submit"
            disabled={!input.trim() || busy || recording}
            aria-label="Gửi tin nhắn"
          >
            <Icon name="send" size={19} />
          </button>
          <small>
            {recording ? "Đang ghi âm · Nhấn micro để dừng" : "Nhấn Enter để gửi · Shift + Enter để xuống dòng"}
          </small>
        </form>
      </div>
    </section>
  );
}
