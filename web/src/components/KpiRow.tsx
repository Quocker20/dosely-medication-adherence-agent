import type { DashboardSummary } from "../types";

interface Props {
  summary: DashboardSummary | null;
}

interface Tile {
  label: string;
  value: number;
  unit?: string;
  foot: string;
  ok: boolean;
  crit?: boolean;
}

export default function KpiRow({ summary }: Props) {
  if (!summary) {
    return <div className="kpi-row" aria-busy="true" />;
  }

  const tiles: Tile[] = [
    {
      label: "Tuân thủ trung bình",
      value: summary.adherence_avg,
      unit: "%",
      foot: "Mục tiêu MVP ≥ 70%",
      ok: summary.adherence_avg >= 70,
    },
    {
      label: "Phản hồi nhắc nhở",
      value: summary.response_minutes,
      unit: " phút",
      foot: "Mục tiêu < 30 phút",
      ok: summary.response_minutes < 30,
    },
    {
      label: "Red Alert đang mở",
      value: summary.open_alerts,
      foot: `Độ chính xác 7 ngày: ${summary.red_alert_precision}%`,
      ok: summary.open_alerts === 0,
      crit: summary.open_alerts > 0,
    },
    {
      label: "Liều bỏ qua hôm nay",
      value: summary.doses_missed_today,
      foot: `trên tổng ${summary.doses_due_today} liều đến hạn`,
      ok: summary.doses_missed_today === 0,
    },
  ];

  return (
    <div className="kpi-row">
      {tiles.map((tile) => (
        <div key={tile.label} className={`card kpi ${tile.crit ? "is-crit" : ""} ${tile.ok ? "is-ok" : "is-warn"}`}>
          <div className="kpi-label">{tile.label}</div>
          <div className="kpi-value">
            {tile.value}
            {tile.unit && <small>{tile.unit}</small>}
          </div>
          <div className="kpi-foot">
            <span className="tick">{tile.ok ? "✓" : "•"}</span>
            <span>{tile.foot}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
