// Health survey read API for Doctor/Admin portal.
// Contract lấy từ nhánh backend fix/getsurvey.

import { request } from "./client";
import type { HealthSurveyFullDetail, HealthSurveyListItem, PageResponse } from "../types";

export const healthSurveysApi = {
  healthSurveys: (
    params: {
      from: string;
      to: string;
      patientId?: string;
      severity?: string;
      page?: number;
      size?: number;
    },
  ) =>
    request<PageResponse<HealthSurveyListItem>>("/health-surveys", {
      query: {
        from: params.from,
        to: params.to,
        patientId: params.patientId,
        severity: params.severity,
        page: params.page ?? 1,
        size: params.size ?? 20,
      },
    }),

  patientHealthSurveys: (
    patientId: string,
    params: { from: string; to: string; page?: number; size?: number },
  ) =>
    request<PageResponse<HealthSurveyListItem>>(`/patients/${patientId}/health-surveys`, {
      query: {
        from: params.from,
        to: params.to,
        page: params.page ?? 1,
        size: params.size ?? 20,
      },
    }),

  healthSurveyDetail: (surveyId: string) =>
    request<HealthSurveyFullDetail>(`/health-surveys/${surveyId}`),
};
