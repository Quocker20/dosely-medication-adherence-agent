// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 8 — Chat & AI Agent History

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: string | null;
  createdAt: string;
}

export interface ChatConversationListItem {
  id: string;
  title: string;
  preview?: string | null;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ChatConversationDetailResponse {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  hasMore: boolean;
  nextCursor?: string | null;
}
