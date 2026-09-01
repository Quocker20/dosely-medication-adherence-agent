// Slice 7: Alerts.
//
// LƯU Ý: banner "Slice 7" trong api.ts gốc gộp cả các endpoint hành động của
// bệnh nhân (dose action, health survey, SOS, chat) dù chúng không liên quan
// alert. Giữ nguyên nhóm này đúng như ranh giới cũ để không bịa ranh giới mới —
// muốn tách riêng thì làm ở một đợt refactor có chủ đích khác.
import { request } from "./client";
import type {
  AdherenceSummary,
  AlertDetail,
  ChatConversationDetailResponse,
  ChatConversationListItem,
  PageResponse,
  VoiceChatResponse,
} from "../types";

export const alertsApi = {
  alerts: (params: { status?: string; patientId?: string; page?: number; size?: number } = {}) =>
    request<PageResponse<AlertDetail>>("/alerts", {
      query: {
        status: params.status,
        patientId: params.patientId,
        page: params.page ?? 1,
        size: params.size ?? 50,
      },
    }),

  acknowledgeAlert: (alertId: string) =>
    request<AlertDetail>(`/alerts/${alertId}/acknowledge`, { method: "POST" }),

  resolveAlert: (alertId: string, resolutionNote: string) =>
    request<AlertDetail>(`/alerts/${alertId}/resolve`, {
      method: "POST",
      body: { resolution_note: resolutionNote },
    }),

  /** from/to là bắt buộc phía backend (Query(...) không default) — dạng YYYY-MM-DD. */
  adherenceSummary: (patientId: string, from: string, to: string) =>
    request<AdherenceSummary>(`/patients/${patientId}/adherence`, { query: { from, to } }),

  recordDoseAction: (
    scheduledDoseId: string,
    action: "TAKEN" | "SNOOZE" | "SKIPPED",
    payload: Record<string, unknown> = {},
  ) =>
    request<null>(`/scheduled-doses/${scheduledDoseId}/actions`, {
      method: "POST",
      body: { action, action_source: "PATIENT_WEB_APP", payload },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    }),

  submitHealthSurvey: (
    patientId: string,
    payload: { survey_date: string; answers_json: Record<string, unknown>; symptoms: Array<{ symptom_code: string; severity: string; description?: string }> },
  ) => request<null>(`/patients/${patientId}/health-surveys`, { method: "POST", body: payload }),

  triggerSos: (patientId: string, message?: string) =>
    request<null>(`/patients/${patientId}/sos`, {
      method: "POST",
      body: { message: message || null },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    }),

  patientChat: (message: string, conversationId?: string, clientDate?: string, clientDateTime?: string) =>
    request<{ response: string; conversationId?: string }>("/chat", {
      method: "POST",
      body: { message, conversationId, clientDate, clientDateTime },
    }),

  patientChatHistory: (conversationId: string) =>
    request<{ conversationId: string; messages: Array<{ id: string; role: "user" | "assistant"; content: string; createdAt: string }> }>(`/chat/${conversationId}`),

  patientChatVoice: (audio: Blob, conversationId?: string, clientDate?: string, clientDateTime?: string) => {
    const formData = new FormData();
    formData.append("audio", audio, "voice-message.webm");
    if (conversationId) formData.append("conversationId", conversationId);
    if (clientDate) formData.append("clientDate", clientDate);
    if (clientDateTime) formData.append("clientDateTime", clientDateTime);
    return request<VoiceChatResponse>("/chat/voice", {
      method: "POST",
      body: formData,
    });
  },

  chatConversations: (page = 1, size = 20) =>
    request<PageResponse<ChatConversationListItem>>("/chat/conversations", {
      query: { page, size },
    }),

  chatConversationDetail: (conversationId: string, limit = 50, before?: string) =>
    request<ChatConversationDetailResponse>(`/chat/conversations/${conversationId}`, {
      query: { limit, before },
    }),
};
