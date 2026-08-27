// Part of src/types/ — schema đọc survey từ nhánh backend fix/getsurvey.
// Nguồn: src/modules/adherence/schemas.py

export type HealthSurveySeverity = "MILD" | "MODERATE" | "SEVERE";

export interface HealthSurveyListItem {
  id: string;
  patient_id: string;
  patient_name: string;
  survey_date: string;
  status: string;
  submitted_at: string | null;
  symptom_count: number;
  max_severity: HealthSurveySeverity | null;
}

export interface SymptomReportDetail {
  id: string;
  survey_id: string | null;
  symptom_code: string;
  severity: HealthSurveySeverity | string;
  description: string | null;
  reported_at: string;
  source: string;
}

export interface HealthSurveyFullDetail {
  id: string;
  patient_id: string;
  patient_name: string;
  survey_date: string;
  status: string;
  submitted_at: string | null;
  answers_json: Record<string, unknown>;
  symptoms: SymptomReportDetail[];
}
