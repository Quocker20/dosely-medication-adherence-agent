// Slice 6: Schedules & Agents
import { request } from "./client";
import type { ActiveSchedule, AgentRunAsyncResponse, AgentRunStatus } from "../types";

export const schedulesApi = {
  /** 202 Accepted — trả agent_run_id, phải poll agentRun() để biết kết quả. */
  generateSchedule: (patientId: string, reason?: string) =>
    request<AgentRunAsyncResponse>(`/patients/${patientId}/schedules/generate`, {
      method: "POST",
      body: { reason: reason ?? null },
    }),

  schedule: (patientId: string, date?: string) =>
    request<ActiveSchedule>(`/patients/${patientId}/schedules`, { query: { date } }),

  agentRun: (agentRunId: string) => request<AgentRunStatus>(`/agent-runs/${agentRunId}`),
};
