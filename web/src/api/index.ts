// Barrel của HTTP client. Mọi nơi khác import từ đây (`from "../api"`), không
// trỏ thẳng vào file slice — gộp/tách slice sau này sẽ không phải sửa call site,
// và cách gọi vẫn phẳng: api.dashboardPatients(...), api.createDoctor(...).

import { adminApi } from "./admin";
import { alertsApi } from "./alerts";
import { authApi } from "./auth";
import { dashboardApi } from "./dashboard";
import { healthSurveysApi } from "./healthSurveys";
import { medicationsApi } from "./medications";
import { patientsApi } from "./patients";
import { prescriptionsApi } from "./prescriptions";
import { routineApi } from "./routine";
import { schedulesApi } from "./schedules";
import type { AgentRunStatus } from "../types";

export { ApiError } from "./client";

export const api = {
  ...authApi,
  ...dashboardApi,
  ...alertsApi,
  ...routineApi,
  ...patientsApi,
  ...medicationsApi,
  ...prescriptionsApi,
  ...schedulesApi,
  ...adminApi,
  ...healthSurveysApi,
};

/**
 * Chờ Planning Agent chạy xong. Agent chạy nền (202) nên không có
 * cách nào lấy lịch ngay trong response — phải poll agent run tới trạng thái
 * cuối. SLO của agent là < 10s; mặc định bỏ cuộc sau ~30s để UI không treo.
 */
export async function waitForAgentRun(
  agentRunId: string,
  options: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<AgentRunStatus> {
  const interval = options.intervalMs ?? 1000;
  const timeout = options.timeoutMs ?? 30_000;
  const startedAt = Date.now();

  // agent_runs.status chỉ ghi RUNNING -> COMPLETED | FAILED
  // (src/modules/agents/repository.py) — không có SUCCESS/NEEDS_REVIEW ở tầng này.
  const terminal = new Set(["COMPLETED", "FAILED"]);

  for (;;) {
    const run = await api.agentRun(agentRunId);
    if (terminal.has(run.status.toUpperCase())) return run;
    if (Date.now() - startedAt > timeout) return run;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}
