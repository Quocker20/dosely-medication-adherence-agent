import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../../../api";
import Icon from "./Icon";

interface ChatMessage { id: string; role: "user" | "assistant"; content: string; time: string }

/** Cache UI theo bệnh nhân; lịch sử chính được lưu và tải từ PostgreSQL. */
export function chatStorageKey(patientId: string) { return `remindrx.patient-chat.${patientId}`; }
function conversationStorageKey(patientId: string) { return `remindrx.patient-conversation.${patientId}`; }

function welcomeChatMessages(): ChatMessage[] {
  return [{ id: "welcome", role: "assistant", content: "Chào bạn! Tôi là trợ lý RemindRx. Tôi có thể giúp bạn tra cứu lịch uống thuốc, giải thích thông tin thuốc từ nguồn tham khảo và ghi nhận vấn đề cần bác sĩ xem xét.", time: "Bây giờ" }];
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return typeof message.id === "string" && (message.role === "user" || message.role === "assistant") && typeof message.content === "string" && typeof message.time === "string";
}

export default function ChatView({ patientId }: { patientId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const stored = window.localStorage.getItem(chatStorageKey(patientId));
      const parsed: unknown = stored ? JSON.parse(stored) : null;
      return Array.isArray(parsed) && parsed.length > 0 && parsed.every(isChatMessage) ? parsed : welcomeChatMessages();
    } catch { return welcomeChatMessages(); }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const conversationIdRef = useRef<string>((() => {
    const key = conversationStorageKey(patientId);
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const created = crypto.randomUUID();
    window.localStorage.setItem(key, created);
    return created;
  })());
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<number | null>(null);
  const discardRecordingRef = useRef(false);
  const voiceSupported = useMemo(() => typeof window !== "undefined" && "MediaRecorder" in window && Boolean(navigator.mediaDevices?.getUserMedia), []);
  const suggestions = ["Liều tiếp theo lúc mấy giờ?", "Quên liều thì nên làm gì?", "Giải thích cách dùng thuốc của tôi"];

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => {
    try { window.localStorage.setItem(chatStorageKey(patientId), JSON.stringify(messages)); } catch { /* Cache is optional. */ }
  }, [messages, patientId]);

  useEffect(() => {
    let cancelled = false;
    api.patientChatHistory(conversationIdRef.current).then((result) => {
      if (cancelled || !result.messages.length) return;
      setMessages(result.messages.map((item) => ({
        id: item.id,
        role: item.role,
        content: item.content,
        time: new Date(item.createdAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
      })));
    }).catch(() => { /* local cache remains visible when history API is unavailable */ });
    return () => { cancelled = true; };
  }, [patientId]);

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
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: message, time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) };
    setMessages((current) => [...current, userMessage]);
    setInput(""); setError(null); setBusy(true);
    try {
      const result = await api.patientChat(message, conversationIdRef.current);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: result.response, time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) }]);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại."); }
    finally { setBusy(false); }
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
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
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
        try {
          const result = await api.patientChatVoice(audio, conversationIdRef.current);
          const time = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
          setMessages((current) => [
            ...current,
            { id: crypto.randomUUID(), role: "user", content: result.transcript, time },
            { id: crypto.randomUUID(), role: "assistant", content: result.response, time },
          ]);
        } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại."); }
        finally { setBusy(false); }
      };
      recorder.start();
      setRecording(true);
      recordingTimeoutRef.current = window.setTimeout(stopRecording, 60_000);
    } catch (cause) {
      stream?.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      setRecording(false);
      setError(cause instanceof DOMException && cause.name === "NotAllowedError" ? "Bạn cần cho phép dùng micro để gửi tin nhắn thoại." : "Không thể bắt đầu ghi âm. Vui lòng thử lại.");
    }
  }

  return <section className="chat-layout">
    <div className="web-card chat-panel">
      <header className="chat-panel-head"><div className="chat-avatar"><Icon name="assistant" size={22}/></div><div><h2>Trợ lý AI</h2><p>Thuốc & lịch uống · RemindRx</p></div><button onClick={() => { conversationIdRef.current = crypto.randomUUID(); window.localStorage.setItem(conversationStorageKey(patientId), conversationIdRef.current); setMessages(welcomeChatMessages()); }}>Cuộc trò chuyện mới</button></header>
      <div className="chat-warning"><Icon name="alert" size={17}/><span>AI chỉ cung cấp thông tin tham khảo; không tự thay đổi liều, kê đơn hoặc xử trí cấp cứu qua chat.</span></div>
      <div className="chat-messages">
        {messages.map((message) => <div key={message.id} className={`chat-row ${message.role}`}><div className="chat-bubble">{message.role === "assistant" && <b>RemindRx AI</b>}<p>{message.content}</p><time>{message.time}</time></div></div>)}
        {busy && <div className="chat-row assistant"><div className="chat-bubble chat-typing"><i/><i/><i/><span>Đang tra cứu…</span></div></div>}
        {error && <div className="chat-error">{error}</div>}
        <div ref={bottomRef}/>
      </div>
      <div className="chat-suggestions">{suggestions.map((suggestion) => <button key={suggestion} disabled={busy || recording} onClick={() => void send(suggestion)}>{suggestion}</button>)}</div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(input); }}><textarea value={input} disabled={recording} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(input); } }} maxLength={5000} rows={1} placeholder="Hỏi về thuốc hoặc lịch uống…"/>{voiceSupported && <button className={`chat-mic ${recording ? "recording" : ""}`} type="button" disabled={busy} onClick={() => { if (recording) stopRecording(); else void startRecording(); }} aria-label={recording ? "Dừng ghi âm" : "Gửi tin nhắn thoại"}><Icon name="mic" size={19}/></button>}<button className="chat-send" type="submit" disabled={!input.trim() || busy || recording} aria-label="Gửi tin nhắn"><Icon name="send" size={19}/></button><small>{recording ? "Đang ghi âm · Nhấn micro để dừng" : "Nhấn Enter để gửi · Shift + Enter để xuống dòng"}</small></form>
    </div>
  </section>;
}
