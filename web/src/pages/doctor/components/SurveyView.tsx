import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../../../api";
import GuardBanner from "../../../components/shared/GuardBanner";
import type {
  DashboardPatientListItem,
  HealthSurveyFullDetail,
  HealthSurveyListItem,
  HealthSurveySeverity,
} from "../../../types";
import { formatDate, formatDateTime, initialsOf, isoDate, paginationRange, patientDisplayName } from "../../../utils/labels";

type SurveyMode = "all" | "patient";

interface Props {
  patients: DashboardPatientListItem[];
  onOpenPatient: (patientId: string) => void;
  onToast: (message: string) => void;
}

const PAGE_SIZE = 20;
const SEVERITY_OPTIONS: { value: "" | HealthSurveySeverity; label: string }[] = [
  { value: "", label: "Mọi mức độ" },
  { value: "MILD", label: "Nhẹ" },
  { value: "MODERATE", label: "Vừa" },
  { value: "SEVERE", label: "Nặng" },
];

const SYMPTOM_LABELS: Record<string, string> = {
  DIZZINESS: "Chóng mặt",
  NAUSEA: "Buồn nôn",
  HEADACHE: "Đau đầu",
  FATIGUE: "Mệt mỏi",
  NONE: "Không có",
};

function mergePatients(
  existing: DashboardPatientListItem[],
  incoming: DashboardPatientListItem[],
): DashboardPatientListItem[] {
  const byId = new Map(existing.map((patient) => [patient.patient_id, patient]));
  incoming.forEach((patient) => byId.set(patient.patient_id, patient));
  return [...byId.values()].sort((a, b) =>
    patientDisplayName(a.patient_name).localeCompare(patientDisplayName(b.patient_name), "vi"),
  );
}

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDate(date);
}

function severityView(severity: string | null): { label: string; tone: "crit" | "warn" | "ok" | "" } {
  if (severity === "SEVERE") return { label: "Nặng", tone: "crit" };
  if (severity === "MODERATE") return { label: "Vừa", tone: "warn" };
  if (severity === "MILD") return { label: "Nhẹ", tone: "ok" };
  return { label: "Không ghi nhận", tone: "" };
}

function answerLabel(key: string): string {
  const labels: Record<string, string> = {
    mood: "Điểm cảm nhận",
    mood_score: "Điểm cảm nhận",
    free_text: "Ghi chú",
    notes: "Ghi chú",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function renderAnswerValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export default function SurveyView({ patients, onOpenPatient, onToast }: Props) {
  const [mode, setMode] = useState<SurveyMode>("all");
  const [fromDate, setFromDate] = useState(daysAgo(30));
  const [toDate, setToDate] = useState(isoDate(new Date()));
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(1);

  const [patientSearch, setPatientSearch] = useState("");
  const [debouncedPatientSearch, setDebouncedPatientSearch] = useState("");
  const [patientOptions, setPatientOptions] = useState<DashboardPatientListItem[]>(patients);
  const [selectedPatientId, setSelectedPatientId] = useState("");

  const [surveys, setSurveys] = useState<HealthSurveyListItem[]>([]);
  const [totalSurveys, setTotalSurveys] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [detail, setDetail] = useState<HealthSurveyFullDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    setPatientOptions((current) => mergePatients(current, patients));
  }, [patients]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedPatientSearch(patientSearch), 300);
    return () => window.clearTimeout(timer);
  }, [patientSearch]);

  useEffect(() => {
    const query = debouncedPatientSearch.trim();
    if (query.length < 2) return;

    let cancelled = false;
    api
      .dashboardPatients({ search: query, size: 25 })
      .then((result) => {
        if (!cancelled) setPatientOptions((current) => mergePatients(current, result.content));
      })
      .catch(() => {
        // Survey list vẫn hoạt động; search bệnh nhân sẽ thử lại ở lần nhập sau.
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedPatientSearch]);

  const selectedPatient = useMemo(
    () => patientOptions.find((patient) => patient.patient_id === selectedPatientId) ?? null,
    [patientOptions, selectedPatientId],
  );

  const refreshSurveys = useCallback(async (): Promise<boolean> => {
    if (fromDate > toDate) {
      setSurveys([]);
      setTotalSurveys(0);
      setLoadError("Khoảng ngày không hợp lệ");
      setLoading(false);
      return false;
    }

    if (mode === "patient" && !selectedPatientId) {
      setSurveys([]);
      setTotalSurveys(0);
      setLoadError(null);
      setLoading(false);
      return false;
    }

    setLoading(true);
    try {
      const result =
        mode === "patient" && selectedPatientId && !severity
          ? await api.patientHealthSurveys(selectedPatientId, {
              from: fromDate,
              to: toDate,
              page,
              size: PAGE_SIZE,
            })
          : await api.healthSurveys({
              from: fromDate,
              to: toDate,
              patientId: mode === "patient" ? selectedPatientId : undefined,
              severity: severity || undefined,
              page,
              size: PAGE_SIZE,
            });
      setSurveys(result.content);
      setTotalSurveys(result.total_elements);
      setLoadError(null);
      return true;
    } catch (error) {
      setSurveys([]);
      setTotalSurveys(0);
      setLoadError(error instanceof ApiError ? error.message : "Không tải được khảo sát");
      return false;
    } finally {
      setLoading(false);
    }
  }, [fromDate, mode, page, selectedPatientId, severity, toDate]);

  useEffect(() => {
    void refreshSurveys();
  }, [refreshSurveys]);

  async function openSurvey(surveyId: string) {
    setDetailBusy(true);
    setDetailError(null);
    try {
      const nextDetail = await api.healthSurveyDetail(surveyId);
      setDetail(nextDetail);
    } catch (error) {
      setDetail(null);
      setDetailError(error instanceof ApiError ? error.message : "Không mở được chi tiết khảo sát");
    } finally {
      setDetailBusy(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalSurveys / PAGE_SIZE));
  const severeOnPage = surveys.filter((survey) => survey.max_severity === "SEVERE").length;
  const latestSurvey = surveys[0]?.survey_date ?? null;
  const selectedSurveyId = detail?.id ?? null;

  return (
    <section className="view">
      <GuardBanner title="Theo dõi khảo sát sức khỏe">
        <li>
          Dữ liệu survey giúp bác sĩ theo dõi triệu chứng và mức độ khó chịu của bệnh nhân theo thời gian.
        </li>
        <li>
          Triệu chứng nặng chỉ tạo cảnh báo để bác sĩ xử lý; hệ thống không tự đổi thuốc, đổi liều hay ngưng thuốc.
        </li>
      </GuardBanner>

      <div className="survey-kpi-row">
        <article className="card kpi">
          <div className="kpi-label">Tổng khảo sát</div>
          <div className="kpi-value">{totalSurveys}</div>
          <div className="kpi-foot">trong khoảng ngày đã chọn</div>
        </article>
        <article className={`card kpi ${severeOnPage > 0 ? "is-crit" : "is-ok"}`}>
          <div className="kpi-label">Mức nặng trên trang</div>
          <div className="kpi-value">{severeOnPage}</div>
          <div className="kpi-foot">
            <span className="tick">●</span>
            cần đối chiếu với cảnh báo
          </div>
        </article>
        <article className="card kpi">
          <div className="kpi-label">Gần nhất</div>
          <div className="kpi-value survey-date-value">{formatDate(latestSurvey)}</div>
          <div className="kpi-foot">{selectedPatient ? patientDisplayName(selectedPatient.patient_name) : "tất cả bệnh nhân"}</div>
        </article>
      </div>

      <div className="survey-workspace">
        <div className="card survey-list-card">
          <div className="card-head">
            <h2>Khảo sát</h2>
            <div className="spacer" />
            <button
              className="btn"
              disabled={loading}
              onClick={() => {
                refreshSurveys()
                  .then((ok) => {
                    if (ok) onToast("Đã đồng bộ khảo sát");
                  })
                  .catch(() => {});
              }}
            >
              ↻ Làm mới
            </button>
          </div>

          <div className="card-body">
            <div className="survey-controls">
              <div className="segmented survey-mode" aria-label="Chế độ xem khảo sát">
                <button
                  className={mode === "all" ? "active" : ""}
                  onClick={() => {
                    setMode("all");
                    setPage(1);
                  }}
                >
                  Tổng hợp
                </button>
                <button
                  className={mode === "patient" ? "active" : ""}
                  onClick={() => {
                    setMode("patient");
                    setPage(1);
                  }}
                >
                  Theo bệnh nhân
                </button>
              </div>

              <label>
                <span>Từ ngày</span>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(event) => {
                    setFromDate(event.target.value);
                    setPage(1);
                  }}
                />
              </label>
              <label>
                <span>Đến ngày</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(event) => {
                    setToDate(event.target.value);
                    setPage(1);
                  }}
                />
              </label>
              <label>
                <span>Mức độ</span>
                <select
                  value={severity}
                  onChange={(event) => {
                    setSeverity(event.target.value);
                    setPage(1);
                  }}
                >
                  {SEVERITY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              {mode === "patient" && (
                <>
                  <label className="survey-patient-search">
                    <span>Tìm bệnh nhân</span>
                    <input
                      placeholder="Tên hoặc SĐT"
                      value={patientSearch}
                      onChange={(event) => setPatientSearch(event.target.value)}
                    />
                  </label>
                  <label className="survey-patient-select">
                    <span>Bệnh nhân</span>
                    <select
                      value={selectedPatientId}
                      onChange={(event) => {
                        setSelectedPatientId(event.target.value);
                        setPage(1);
                        setDetail(null);
                      }}
                    >
                      <option value="">Chọn bệnh nhân</option>
                      {patientOptions.map((patient) => (
                        <option key={patient.patient_id} value={patient.patient_id}>
                          {patientDisplayName(patient.patient_name)} · {patient.patient_id.slice(0, 8)}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
            </div>

            {loadError && (
              <div className="errors">
                <b>Không tải được dữ liệu survey</b>
                <ul>
                  <li>{loadError}</li>
                </ul>
              </div>
            )}

            <div className="table-wrap">
              <table className="survey-table">
                <thead>
                  <tr>
                    <th>Bệnh nhân</th>
                    <th>Ngày khảo sát</th>
                    <th>Triệu chứng</th>
                    <th>Mức cao nhất</th>
                    <th>Đã nộp</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {surveys.map((survey) => {
                    const severityMeta = severityView(survey.max_severity);
                    const patientName = patientDisplayName(survey.patient_name);
                    const isSelected = survey.id === selectedSurveyId;

                    return (
                      <tr
                        key={survey.id}
                        className={isSelected ? "is-selected" : ""}
                        role="button"
                        tabIndex={0}
                        aria-label={`Mở khảo sát ngày ${formatDate(survey.survey_date)} của ${patientName}`}
                        onClick={() => void openSurvey(survey.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            void openSurvey(survey.id);
                          }
                        }}
                      >
                        <td>
                          <div className="who">
                            <div className="avatar">{initialsOf(survey.patient_name)}</div>
                            <div>
                              <div className="who-name">{patientName}</div>
                              <div className="who-meta mono">{survey.patient_id.slice(0, 8)}</div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="cell-note">{formatDate(survey.survey_date)}</span>
                        </td>
                        <td>
                          <span className="cell-note">
                            {survey.symptom_count > 0 ? `${survey.symptom_count} ghi nhận` : "Không có"}
                          </span>
                        </td>
                        <td>
                          <span className={`pill flat ${severityMeta.tone}`}>
                            {severityMeta.tone && <span className="dot" />}
                            {severityMeta.label}
                          </span>
                        </td>
                        <td>
                          <span className="cell-note">{formatDateTime(survey.submitted_at)}</span>
                        </td>
                        <td>
                          <span className="pill mono">{survey.status}</span>
                        </td>
                      </tr>
                    );
                  })}

                  {!loading && surveys.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <p className="empty">Không có khảo sát trong phạm vi đã chọn.</p>
                      </td>
                    </tr>
                  )}

                  {loading && (
                    <tr>
                      <td colSpan={6}>
                        <p className="empty">Đang tải khảo sát…</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <nav className="row-actions pager" aria-label="Phân trang khảo sát">
              <button
                className="pager-btn"
                disabled={page <= 1 || loading}
                onClick={() => setPage((current) => current - 1)}
              >
                ← Trước
              </button>
              {paginationRange(page, totalPages).map((item, index) =>
                item === "ellipsis" ? (
                  <span key={`survey-ellip-${index}`} className="pager-ellip">
                    …
                  </span>
                ) : (
                  <button
                    key={item}
                    className={`pager-btn ${item === page ? "active" : ""}`}
                    aria-current={item === page}
                    disabled={loading}
                    onClick={() => setPage(item)}
                  >
                    {item}
                  </button>
                ),
              )}
              <button
                className="pager-btn"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((current) => current + 1)}
              >
                Sau →
              </button>
            </nav>
          </div>
        </div>

        <aside className="card survey-detail-card" aria-label="Chi tiết khảo sát">
          <div className="card-head">
            <h2>Chi tiết</h2>
            <div className="spacer" />
            {detail && (
              <button className="btn sm ghost" onClick={() => onOpenPatient(detail.patient_id)}>
                Mở hồ sơ
              </button>
            )}
          </div>
          <div className="card-body">
            {detailBusy && <p className="empty">Đang tải chi tiết…</p>}
            {detailError && (
              <div className="errors">
                <b>Không mở được chi tiết</b>
                <ul>
                  <li>{detailError}</li>
                </ul>
              </div>
            )}
            {!detailBusy && !detailError && !detail && (
              <p className="empty">Chọn một khảo sát để xem câu trả lời và triệu chứng.</p>
            )}

            {!detailBusy && detail && (
              <>
                <div className="survey-detail-head">
                  <div className="who">
                    <div className="avatar">{initialsOf(detail.patient_name)}</div>
                    <div>
                      <div className="who-name">{patientDisplayName(detail.patient_name)}</div>
                      <div className="who-meta mono">{detail.patient_id.slice(0, 8)}</div>
                    </div>
                  </div>
                  <div className="routine">
                    <span className="pill mono">{formatDate(detail.survey_date)}</span>
                    <span className="pill mono">{detail.status}</span>
                  </div>
                </div>

                <div className="drawer-sec">
                  <div className="eyebrow">Câu trả lời</div>
                  <div className="survey-answer-list">
                    {Object.entries(detail.answers_json).length === 0 ? (
                      <p className="rail-note">Không có câu trả lời dạng JSON.</p>
                    ) : (
                      Object.entries(detail.answers_json).map(([key, value]) => (
                        <div className="survey-answer-row" key={key}>
                          <span>{answerLabel(key)}</span>
                          <b>{renderAnswerValue(value)}</b>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="drawer-sec">
                  <div className="eyebrow">Triệu chứng</div>
                  {detail.symptoms.length === 0 ? (
                    <p className="rail-note">Không ghi nhận triệu chứng.</p>
                  ) : (
                    <div className="log">
                      {detail.symptoms.map((symptom) => {
                        const symptomSeverity = severityView(symptom.severity);
                        return (
                          <div className="log-row survey-symptom-row" key={symptom.id}>
                            <div className="log-time">{formatDateTime(symptom.reported_at)}</div>
                            <div className="log-what">
                              <div className="survey-symptom-title">
                                <b>{SYMPTOM_LABELS[symptom.symptom_code] ?? symptom.symptom_code}</b>
                                <span className={`pill flat ${symptomSeverity.tone}`}>
                                  {symptomSeverity.tone && <span className="dot" />}
                                  {symptomSeverity.label}
                                </span>
                              </div>
                              {symptom.description && <p>{symptom.description}</p>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
