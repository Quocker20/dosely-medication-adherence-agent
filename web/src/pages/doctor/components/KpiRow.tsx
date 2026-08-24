import { adherenceTone } from "../../../utils/labels";
import type { AlertDetail, DashboardPatientListItem } from "../../../types";

interface Props {
  patients: DashboardPatientListItem[];
  alerts: AlertDetail[];
  totalPatients: number;
  loading: boolean;
}

interface Tile {
  label: string;
  value: string;
  foot: string;
  tone: "ok" | "warn" | "crit";
}

/**
 * Backend không có endpoint tổng hợp (/dashboard/summary từng được gọi ở đây
 * chưa từng tồn tại) — các chỉ số dưới đây tính từ roster + danh sách cảnh báo
 * đang tải, nên phạm vi của chúng đúng bằng phạm vi của bác sĩ đang đăng nhập.
 */
export default function KpiRow({ patients, alerts, totalPatients, loading }: Props) {
  if (loading) {
    return <div className="kpi-row" aria-busy="true" />;
  }

  const avgAdherence =
    patients.length > 0
      ? Math.round(patients.reduce((sum, p) => sum + p.adherence_rate, 0) / patients.length)
      : 0;

  const openAlerts = alerts.filter((alert) => alert.status === "OPEN").length;
  const acknowledged = alerts.filter((alert) => alert.status === "ACKNOWLEDGED").length;
  const watching = patients.filter((p) => p.open_alerts_count === 0 && p.adherence_rate < 70).length;

  const tiles: Tile[] = [
    {
      label: "Bệnh nhân đang theo dõi",
      value: String(totalPatients),
      foot: `${patients.length} dòng đang hiển thị`,
      tone: "ok",
    },
    {
      label: "Tuân thủ trung bình",
      value: `${avgAdherence}%`,
      foot: "Mục tiêu MVP ≥ 70%",
      tone: adherenceTone(avgAdherence),
    },
    {
      label: "Cảnh báo đang mở",
      value: String(openAlerts),
      foot: `${acknowledged} đã tiếp nhận, chờ xử lý`,
      tone: openAlerts > 0 ? "crit" : "ok",
    },
    {
      label: "Cần theo dõi",
      value: String(watching),
      foot: "Tuân thủ < 70%, chưa có cảnh báo",
      tone: watching > 0 ? "warn" : "ok",
    },
  ];

  return (
    <div className="kpi-row">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className={`card kpi ${tile.tone === "crit" ? "is-crit" : ""} ${tile.tone === "ok" ? "is-ok" : "is-warn"}`}
        >
          <div className="kpi-label">{tile.label}</div>
          <div className="kpi-value">{tile.value}</div>
          <div className="kpi-foot">
            <span className="tick">{tile.tone === "ok" ? "✓" : "•"}</span>
            <span>{tile.foot}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
